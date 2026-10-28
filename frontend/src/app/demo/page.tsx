import type { Metadata } from "next";
import { DemoGuide } from "@/components/demo/demo-guide";

export const metadata: Metadata = { title: "Keyless demo guide" };

export default function DemoPage() {
  return <DemoGuide />;
}
