import type { CleanupTicket } from "@/lib/api/source-contracts";

export interface SourceActionState {
  status: "idle" | "error" | "success";
  message: string;
  version: number;
  cleanup?: CleanupTicket;
}

export const INITIAL_SOURCE_ACTION: SourceActionState = { status: "idle", message: "", version: 0 };
