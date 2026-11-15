// Bound runner startup overhead without dropping tests from the selected suite.
const [countInput, limitInput = "16"] = process.argv.slice(2);
const count = Number(countInput);
const limit = Number(limitInput);

if (
  !Number.isSafeInteger(count) || count < 1 ||
  !Number.isSafeInteger(limit) || limit < 1 || limit > 70
) {
  console.error("Expected a positive test count and an integer shard limit from 1 to 70.");
  process.exitCode = 1;
} else {
  const total = Math.min(limit, Math.ceil(count / 20));
  const include = Array.from({ length: total }, (_, i) => ({ shardIndex: i + 1, shardTotal: total }));
  console.log(`matrix=${JSON.stringify({ include })}`);
  console.log(`shard_count=${total}`);
}
