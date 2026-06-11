import { Router, type IRouter } from "express";
import { getLatestSnapshot, getSnapshotById, listSnapshots, captureSnapshot } from "../services/snapshot";

const router: IRouter = Router();

router.get("/snapshots/latest", async (req, res): Promise<void> => {
  const type = req.query.type as "all-stocks" | "all-etfs" | "all-combined" | undefined;
  if (!type || !["all-stocks", "all-etfs", "all-combined"].includes(type)) {
    res.status(400).json({ error: "type query param is required (all-stocks | all-etfs | all-combined)" });
    return;
  }

  const snapshot = await getLatestSnapshot(type);
  if (!snapshot) {
    res.status(404).json({ error: "No snapshot found" });
    return;
  }

  res.json(snapshot);
});

router.get("/snapshots", async (_req, res): Promise<void> => {
  const snapshots = await listSnapshots();
  res.json({ snapshots });
});

router.get("/snapshots/:id", async (req, res): Promise<void> => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) {
    res.status(400).json({ error: "Invalid id" });
    return;
  }

  const snapshot = await getSnapshotById(id);
  if (!snapshot) {
    res.status(404).json({ error: "Snapshot not found" });
    return;
  }

  res.json(snapshot);
});

router.post("/snapshots/trigger", async (req, res): Promise<void> => {
  const type = req.body.type as "all-stocks" | "all-etfs" | "all-combined";
  if (!type || !["all-stocks", "all-etfs", "all-combined"].includes(type)) {
    res.status(400).json({ error: "type must be all-stocks | all-etfs | all-combined" });
    return;
  }

  captureSnapshot(type);
  res.json({ message: `Snapshot capture started for ${type}` });
});

export default router;
