'use strict';
// Runs several command lines of sor.js in one process, for the tests that compare it with the Python tool: node readall.js JOBS.json,
// where JOBS.json is a list of argument lists. Prints a list of {code, out} in the same order.
const fs = require('fs');
const { run } = require('../sor');

const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
process.stdout.write(JSON.stringify(jobs.map((argv) => { const { code, out } = run(argv); return { code, out }; })));
