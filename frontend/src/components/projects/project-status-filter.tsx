import Link from "next/link";

import type { ProjectListStatus } from "@/lib/api/contracts";

interface ProjectStatusFilterProps {
  selected: ProjectListStatus;
}

const FILTERS: Array<{ value: ProjectListStatus; label: string }> = [
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
  { value: "all", label: "All" },
];

export function ProjectStatusFilter({ selected }: ProjectStatusFilterProps) {
  return (
    <nav className="status-filter" aria-label="Filter projects by status">
      {FILTERS.map((filter) => {
        const href = filter.value === "active" ? "/projects" : `/projects?status=${filter.value}`;
        return (
          <Link
            key={filter.value}
            href={href}
            className="status-filter__link"
            aria-current={selected === filter.value ? "page" : undefined}
          >
            {filter.label}
          </Link>
        );
      })}
    </nav>
  );
}
