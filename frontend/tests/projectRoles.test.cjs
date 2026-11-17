const fs = require('node:fs');
const test = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

// Exercise the actual TSX component with existing build dependencies; no DOM,
// network requests, or additional test packages are needed for server rendering.
for (const extension of ['.ts', '.tsx']) {
  require.extensions[extension] = (module, filename) => {
    const result = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      fileName: filename,
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
        target: ts.ScriptTarget.ES2020,
        esModuleInterop: true
      }
    });
    module._compile(result.outputText, filename);
  };
}
const ProjectManager = require('../src/components/ProjectManager.tsx').default;

for (const admin of [false, 0, true, 1]) {
  test(`project table renders valid role columns for admin=${admin}`, () => {
    const html = renderToStaticMarkup(React.createElement(ProjectManager, {
      user: { id: 'test-user', username: 'test', admin, active: true }, onClose() {}
    }));
    const columns = html.match(/<colgroup>(.*?)<\/colgroup>/s)[1];
    const header = html.match(/<thead>(.*?)<\/thead>/s)[1];
    assert.equal((columns.match(/<col\b/g) || []).length, admin ? 5 : 4);
    assert.equal((header.match(/<th\b/g) || []).length, admin ? 5 : 4);
    assert.equal(columns.includes('0'), false, 'numeric false leaked into table markup');
    assert.equal(header.includes('0'), false, 'numeric false leaked into table header');
    assert.equal(header.includes('所属账户'), Boolean(admin));
    assert.ok(html.includes(admin ? 'project-table-admin' : 'project-table-own'));
    assert.equal(html.includes('>0<'), false, 'numeric false rendered as standalone text');
  });
}
