import { pgTable, serial, timestamp, text, integer, jsonb } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export const marketSnapshotTypeEnum = z.enum(["all-stocks", "all-etfs", "all-combined"]);
export type MarketSnapshotType = z.infer<typeof marketSnapshotTypeEnum>;

export const marketSnapshotsTable = pgTable("market_snapshots", {
  id: serial("id").primaryKey(),
  type: text("type", { enum: ["all-stocks", "all-etfs", "all-combined"] }).notNull(),
  tradeDate: text("trade_date").notNull(),
  fetchedAt: timestamp("fetched_at", { withTimezone: true }).notNull().defaultNow(),
  symbolCount: integer("symbol_count").notNull(),
  results: jsonb("results").notNull(),
});

export const insertMarketSnapshotSchema = createInsertSchema(marketSnapshotsTable).omit({
  id: true,
  fetchedAt: true,
});

export type InsertMarketSnapshot = z.infer<typeof insertMarketSnapshotSchema>;
export type MarketSnapshot = typeof marketSnapshotsTable.$inferSelect;
