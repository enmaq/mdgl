// @enmaq/mdgl: MDGL 0.1 parser and checker (development tree; evaluator and
// rendering are not implemented yet). Spec: ../SPEC.md
export const VERSION: string = '0.3.1';
export { check, checkDocument, parseChecked } from './check';
export type { CheckedAction, CheckedDocument, CheckedScene, Fallback, ParseResult } from './check';
export { parse } from './parse';
export type { ActionStmt, ActorStmt, Arg, Coord, Diag, Document, Point, SceneStmt, Shape, Stmt, Value } from './parse';
/** Alias of Diag. */
export type Problem = import('./parse').Diag;
/** Result of check(): empty means valid. */
export type CheckResult = import('./parse').Diag[];
export { UNICODE_VERSION, cellRune, clusterWidth, graphemeCount, graphemeRanges, graphemes } from './unicode';
export { compile, compileDocument, frameNs, fallbackFrame } from './eval';
export type { Cell, Compiled, CompileResult, Frame } from './eval';
export { handleLine, mathInt, MAX_REQUEST_LINE } from "./adapter";
export { play, plainFallback, plainText, sanitizeRune, SYNC_BEGIN, SYNC_END, HIDE_CURSOR, SHOW_CURSOR, RESET } from './play';
export type { Clock, PlayDeps, PlayEnd, PlayHandle, PlayResult } from './play';
