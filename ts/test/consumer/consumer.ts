// Typed consumer: type-checked only (tsc --noEmit). Imports "@enmaq/mdgl" (resolved by paths locally, installed package when packed).
import { check, VERSION, CheckResult, Problem } from '@enmaq/mdgl';

const r: CheckResult = check('scene width=8 height=1 fallback=end\n');
const first: Problem | undefined = r[0];
const v: string = VERSION;
const n: number = r.length;
const msgs: string[] = check('x').map((p: Problem) => `${p.line}:${p.col} ${p.message}`);
void [first, v, n, msgs];

// @ts-expect-error source must be a string
check(42);
