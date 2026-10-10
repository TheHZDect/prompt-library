#!/usr/bin/env node
// 把技能包安装到本机 agent 技能目录（对齐 awesome-gpt-image-2 的 install-style-skill.mjs）。
// 用法：node agents/skills/prompt-library/bin/install.mjs [all|codex|claude|agents]
import { cpSync, existsSync, rmSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, '..');                       // agents/skills/prompt-library
const repoRoot = dirname(dirname(dirname(source)));    // <repo>/agents/skills/prompt-library -> <repo>
const skillName = 'prompt-library';
const targets = {
  codex: join(process.env.CODEX_HOME || join(homedir(), '.codex'), 'skills'),
  'claude-code': join(process.env.CLAUDE_HOME || join(homedir(), '.claude'), 'skills'),
  agents: join(process.env.AGENTS_HOME || join(homedir(), '.agents'), 'skills'),
  trae: join(process.env.TRAE_HOME || join(homedir(), '.trae-cn'), 'skills'),
};
const alias = { all: Object.keys(targets), claude: ['claude-code'], shared: ['agents'] };

if (!existsSync(join(source, 'SKILL.md'))) {
  console.error(`技能源缺失：${join(source, 'SKILL.md')}`);
  process.exit(1);
}

const picked = process.argv.slice(2).flatMap((a) => alias[a] || [a]);
const names = picked.length === 0 ? Object.keys(targets) : [...new Set(picked)];

for (const name of names) {
  const root = targets[name];
  if (!root) { console.warn(`未知目标：${name}（可用 all|codex|claude|agents）`); continue; }
  const dst = join(root, skillName);
  mkdirSync(root, { recursive: true });
  rmSync(dst, { recursive: true, force: true });
  cpSync(source, dst, {
    recursive: true,
    filter: (p) => !/[\\/](\.cache|__pycache__|node_modules)[\\/]/.test(p + '/'),
  });
  // 把仓库根烧进技能包：query_lib2 读 <dst>/bin/lib_home.txt 定位 .cache/ 与 assets/thumbs/，
  // 技能装到任何目录、任何 cwd 都不需要环境变量。
  mkdirSync(join(dst, 'bin'), { recursive: true });
  writeFileSync(join(dst, 'bin', 'lib_home.txt'), repoRoot + '\n');
  console.log(`已安装 ${name} -> ${dst}  (lib_home=${repoRoot})`);
}
console.log('\n检索库路径已烧进各技能目录 bin/lib_home.txt；如需临时改道可设环境变量 PROMPT_LIB_HOME=<仓库根>。');
