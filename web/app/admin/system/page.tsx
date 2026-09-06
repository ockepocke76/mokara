import type { Metadata } from "next";

import { SystemActions } from "./system-actions";

export const metadata: Metadata = { title: "Admin · System" };

export default function AdminSystemPage() {
  return <SystemActions />;
}
