import { useCallback, useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import type { Node } from "@xyflow/react";
import {
  applyPositionSnapshot,
  positionsEqual,
  savePositionSnapshot,
  snapshotNodePositions,
  type PositionMap,
} from "@/flow/utils/positions";

const MAX_HISTORY = 80;

interface PositionUndoRedoOptions {
  nodes: Node[];
  setNodes: Dispatch<SetStateAction<Node[]>>;
  positionScope: string;
  isTracked?: (node: Node) => boolean;
}

export function usePositionUndoRedo({
  nodes,
  setNodes,
  positionScope,
  isTracked = () => true,
}: PositionUndoRedoOptions) {
  const nodesRef = useRef(nodes);
  const undoStackRef = useRef<PositionMap[]>([]);
  const redoStackRef = useRef<PositionMap[]>([]);
  const dragStartSnapshotRef = useRef<PositionMap | null>(null);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    undoStackRef.current = [];
    redoStackRef.current = [];
    dragStartSnapshotRef.current = null;
  }, [positionScope]);

  const snapshot = useCallback(
    () => snapshotNodePositions(nodesRef.current, isTracked),
    [isTracked]
  );

  const restoreSnapshot = useCallback(
    (target: PositionMap) => {
      setNodes((current) => {
        const next = applyPositionSnapshot(current, target);
        nodesRef.current = next;
        savePositionSnapshot(positionScope, target);
        return next;
      });
    },
    [positionScope, setNodes]
  );

  const handleNodeDragStart = useCallback(() => {
    dragStartSnapshotRef.current = snapshot();
  }, [snapshot]);

  const handleNodeDragStop = useCallback(
    (_: unknown, node: Node, draggedNodes?: Node[]) => {
      const before = dragStartSnapshotRef.current;
      dragStartSnapshotRef.current = null;
      if (!before || !isTracked(node)) return;

      const after = { ...snapshot() };
      for (const draggedNode of draggedNodes && draggedNodes.length > 0 ? draggedNodes : [node]) {
        if (!isTracked(draggedNode)) continue;
        after[draggedNode.id] = {
          x: draggedNode.position.x,
          y: draggedNode.position.y,
        };
      }
      if (positionsEqual(before, after)) return;

      undoStackRef.current = [...undoStackRef.current, before].slice(-MAX_HISTORY);
      redoStackRef.current = [];
      savePositionSnapshot(positionScope, after);
    },
    [isTracked, positionScope, snapshot]
  );

  const saveCurrent = useCallback(() => {
    savePositionSnapshot(positionScope, snapshot());
  }, [positionScope, snapshot]);

  const undo = useCallback(() => {
    const previous = undoStackRef.current.pop();
    if (!previous) return;

    const current = snapshot();
    if (!positionsEqual(previous, current)) {
      redoStackRef.current = [...redoStackRef.current, current].slice(-MAX_HISTORY);
    }
    restoreSnapshot(previous);
  }, [restoreSnapshot, snapshot]);

  const redo = useCallback(() => {
    const next = redoStackRef.current.pop();
    if (!next) return;

    const current = snapshot();
    if (!positionsEqual(next, current)) {
      undoStackRef.current = [...undoStackRef.current, current].slice(-MAX_HISTORY);
    }
    restoreSnapshot(next);
  }, [restoreSnapshot, snapshot]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (isEditableTarget(target)) return;
      if (!(event.metaKey || event.ctrlKey)) return;
      const key = event.key.toLowerCase();

      if (key === "s") {
        event.preventDefault();
        saveCurrent();
        return;
      }

      if (key !== "z") return;

      event.preventDefault();
      if (event.shiftKey) redo();
      else undo();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [redo, saveCurrent, undo]);

  return { handleNodeDragStart, handleNodeDragStop, undo, redo, saveCurrent };
}

function isEditableTarget(target: HTMLElement | null): boolean {
  if (!target) return false;
  if (target.isContentEditable) return true;
  return ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}
