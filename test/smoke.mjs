#!/usr/bin/env node
/**
 * 离线冒烟：不启动宿主，直接给插件半边喂一个假的 ctx，验证：
 *   1. package.json 的 name / version / dsh.bundle 与代码一致
 *   2. provider 能列出 3 个技能，字段齐全、名字合法
 *   3. 每个技能的 get() 能读到正文，且 frontmatter 已被剥掉
 *   4. resourceBase 指向的技能目录里 SKILL.md / references / samples / scripts 都在
 *   5. apply() 会调用 ctx.skills.registerProvider，卸载时不抛
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import url from "node:url";

const here = path.dirname(url.fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const mod = await import(url.pathToFileURL(path.join(root, "lib", "index.js")).href);

const checks = [];
function check(name, fn) {
  try {
    fn();
    checks.push({ name, ok: true });
    console.log(`  ✔ ${name}`);
  } catch (error) {
    checks.push({ name, ok: false });
    console.log(`  ✘ ${name} — ${error.message}`);
  }
}

console.log(`plugin ${pkg.name}@${pkg.version}`);

check("package.json name 与宿主 name 一致", () => {
  assert.equal(pkg.name, mod.name);
  assert.equal(pkg.name, "dsh-guofeng-studio");
});

check("VERSION 与 package.json 一致", () => {
  assert.equal(mod.VERSION, pkg.version);
});

check("dsh.bundle.patch 指向存在的补丁文件", () => {
  assert.equal(pkg.dsh.bundle.patch, "./cordis.patch.yml");
  assert.ok(fs.existsSync(path.join(root, pkg.dsh.bundle.patch)));
});

check("补丁文件 insert 行的 name 等于包名", () => {
  const yml = fs.readFileSync(path.join(root, "cordis.patch.yml"), "utf8");
  const match = /name:\s*(\S+)/.exec(yml);
  assert.ok(match, "补丁里找不到 name 行");
  assert.equal(match[1], pkg.name);
});

check("inject 声明了 skills", () => {
  assert.deepEqual(mod.inject, ["skills"]);
});

// --- provider ---
let provider = null;
const fakeCtx = {
  skills: {
    registerProvider(create) {
      provider = create({ signal: new AbortController().signal, invalidate() {} });
      return () => {};
    },
  },
};
mod.apply(fakeCtx);

check("apply() 注册了 provider", () => {
  assert.ok(provider, "ctx.skills.registerProvider 没有被调用");
  assert.equal(provider.name, mod.__test.PROVIDER);
});

const candidates = await provider.list();

check("list() 返回 3 个技能", () => {
  assert.equal(candidates.length, 3);
  assert.deepEqual(
    candidates.map((item) => item.name).sort(),
    ["guofeng-lyricist", "guofeng-music-composer", "guofeng-song-studio"],
  );
});

check("候选字段齐全（排名 / 来源 / provider / resourceBase）", () => {
  for (const item of candidates) {
    assert.match(item.name, /^[a-z0-9]+(?:-[a-z0-9]+)*$/);
    assert.ok(item.description.length > 40, `${item.name} description 太短`);
    assert.equal(item.provider, mod.__test.PROVIDER);
    assert.equal(item.rank, mod.__test.RANK);
    assert.equal(item.invocation.modelInvocable, true);
    assert.equal(item.resourceBase.kind, "directory");
    assert.ok(fs.existsSync(item.resourceBase.path), `${item.name} 资源目录不存在`);
  }
});

for (const candidate of candidates) {
  const loaded = await provider.get(candidate);
  check(`${candidate.name} get() 有正文且 frontmatter 已剥离`, () => {
    assert.ok(loaded, "get() 返回 undefined");
    assert.ok(loaded.content.length > 1500, "正文过短");
    assert.ok(!loaded.content.startsWith("---"), "正文仍以 frontmatter 开头");
    assert.equal(loaded.name, candidate.name);
    assert.ok(loaded.content.includes("##"), "正文不像 Markdown");
  });
}

check("技能目录包含 references / samples / scripts", () => {
  const rootDir = mod.__test.SKILLS_ROOT;
  for (const dir of ["guofeng-music-composer", "guofeng-lyricist"]) {
    for (const sub of ["references", "samples", "scripts"]) {
      const target = path.join(rootDir, dir, sub);
      assert.ok(fs.existsSync(target), `${dir}/${sub} 缺失`);
      assert.ok(fs.readdirSync(target).length > 0, `${dir}/${sub} 是空的`);
    }
  }
});

check("总入口技能有 SKILL.md", () => {
  const target = path.join(mod.__test.SKILLS_ROOT, "guofeng-song-studio", "SKILL.md");
  assert.ok(fs.existsSync(target));
  assert.ok(fs.statSync(target).size > 1000);
});

check("package.json files 覆盖 lib / assets / 法律文件", () => {
  const files = pkg.files;
  for (const item of ["lib/index.js", "assets/icon.png", "cordis.patch.yml", "README.md", "README.zh.md", "LICENSE", "NOTICE.md"]) {
    assert.ok(files.includes(item), `files 缺少 ${item}`);
  }
  assert.ok(files.some((item) => item.startsWith("assets/skills")), "files 缺少 assets/skills");
});

check("图标是 512×512 PNG", () => {
  const buf = fs.readFileSync(path.join(root, "assets", "icon.png"));
  assert.deepEqual([...buf.subarray(0, 8)], [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const width = buf.readUInt32BE(16);
  const height = buf.readUInt32BE(20);
  assert.equal(width, 512);
  assert.equal(height, 512);
  assert.ok(buf.length < 500 * 1024, "图标超过 500KB");
});

const failed = checks.filter((item) => !item.ok);
console.log("");
if (failed.length > 0) {
  console.log(`FAILED: ${failed.map((item) => item.name).join("; ")}`);
  process.exit(1);
}
console.log(`SMOKE OK (${checks.length} checks)`);
