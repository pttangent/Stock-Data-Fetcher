import { Router, type IRouter } from "express";
import healthRouter from "./health";
import stocksRouter from "./stocks";
import batchSummaryRouter from "./batchSummary";

const router: IRouter = Router();

router.use(healthRouter);
router.use(stocksRouter);
router.use(batchSummaryRouter);

export default router;
