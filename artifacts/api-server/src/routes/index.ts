import { Router, type IRouter } from "express";
import healthRouter from "./health";
import stocksRouter from "./stocks";
import batchSummaryRouter from "./batchSummary";
import snapshotsRouter from "./snapshots";

const router: IRouter = Router();

router.use(healthRouter);
router.use(stocksRouter);
router.use(batchSummaryRouter);
router.use(snapshotsRouter);

export default router;
