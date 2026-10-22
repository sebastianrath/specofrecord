'use strict';

const LINE_BREAK = /\r\n|\r|\n/;

/**
 * The lines of a text, numbered the way an editor numbers them: a line ends at LF, CRLF or CR and nowhere else. `String.split` on
 * `\n` would keep the CR, and a split at every Unicode separator would give lines after U+2028 a number no editor shows.
 */
function splitLines(text) {
  const lines = text.split(LINE_BREAK);
  if (lines.length && lines[lines.length - 1] === '') lines.pop();
  return lines;
}

module.exports = { splitLines };
