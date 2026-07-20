import { Router, type IRouter } from "express";
import healthRouter from "./health";
import stocksRouter from "./stocks";
import batchSummaryRouter from "./batchSummary";
import secEvidenceRouter from "./secEvidence";

const router: IRouter = Router();
let snapshotsRouterPromise: Promise<typeof import("./snapshots")> | null = null;

router.use(healthRouter);
router.use(stocksRouter);
router.use(batchSummaryRouter);
router.use(secEvidenceRouter);

// Snapshot storage is optional for stock/SEC queries. Load the DB-backed router
// only when a database is configured so the rest of the API can start normally.
router.use(async (req, res, next): Promise<void> => {
  if (!req.path.startsWith("/snapshots")) {
    next();
    return;
  }

  if (!process.env.DATABASE_URL) {
    res.status(503).json({
      error: "Snapshot storage is unavailable because DATABASE_URL is not configured",
    });
    return;
  }

  try {
    snapshotsRouterPromise ??= import("./snapshots");
    const { default: snapshotsRouter } = await snapshotsRouterPromise;
    snapshotsRouter(req, res, next);
  } catch (error) {
    next(error);
  }
});

export default router;
