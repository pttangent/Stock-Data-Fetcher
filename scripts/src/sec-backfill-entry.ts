if (process.argv[2] === "--") {
  process.argv.splice(2, 1);
}

await import("./sec-backfill");
