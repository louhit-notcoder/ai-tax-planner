#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

let ts;
for (const candidate of [
  'typescript',
  '/opt/nvm/versions/node/v22.16.0/lib/node_modules/typescript',
]) {
  try {
    ts = require(candidate);
    break;
  } catch (_) {}
}
if (!ts) {
  throw new Error('TypeScript parser is unavailable. Install frontend dependencies first.');
}

const root = path.resolve(__dirname, '../frontend/src');
const files = [];
function walk(dir) {
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) walk(full);
    else if (/\.(js|jsx|ts|tsx)$/.test(name)) files.push(full);
  }
}
walk(root);

function scriptKind(file) {
  if (file.endsWith('.tsx')) return ts.ScriptKind.TSX;
  if (file.endsWith('.ts')) return ts.ScriptKind.TS;
  if (file.endsWith('.jsx')) return ts.ScriptKind.JSX;
  return ts.ScriptKind.JS;
}

const errors = [];
for (const file of files) {
  const source = fs.readFileSync(file, 'utf8');
  const sourceFile = ts.createSourceFile(
    file,
    source,
    ts.ScriptTarget.ES2022,
    true,
    scriptKind(file),
  );
  for (const diagnostic of sourceFile.parseDiagnostics || []) {
    const pos = diagnostic.start !== undefined
      ? sourceFile.getLineAndCharacterOfPosition(diagnostic.start)
      : null;
    errors.push(
      `${path.relative(root, file)}${pos ? `:${pos.line + 1}:${pos.character + 1}` : ''} ` +
      ts.flattenDiagnosticMessageText(diagnostic.messageText, ' '),
    );
  }
}

if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}
console.log(`Parsed ${files.length} frontend JS/JSX/TS/TSX files successfully.`);
