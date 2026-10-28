import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ProjectLifecycleControls } from "@/components/projects/project-lifecycle-controls";
import { ProjectRenameForm } from "@/components/projects/project-rename-form";
import { ApiErrorState, Notice } from "@/components/ui/api-state";
import { getProject } from "@/lib/api/client";
import { listSourceInventory } from "@/lib/api/sources";
import { ProjectEvidenceWorkspace } from "@/components/projects/project-evidence-workspace";
import { getRuntimeConfiguration, getHistory, listConversations } from "@/lib/api/chat";
import type { AnswerMode, RetrievalMode, Conversation, History } from "@/lib/api/chat-contracts";
import type { PlaylistItem, SourceItem } from "@/lib/api/source-contracts";
import type { Project } from "@/lib/api/contracts";
import { ApiError, errorReference, publicErrorMessage } from "@/lib/api/errors";
import { getAudioCapability } from '@/lib/api/audio';
import { getVideoCapability } from '@/lib/api/video';

export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata: Metadata = {
  title: "Project details",
};

interface ProjectPageProps {
  params: Promise<{ projectId: string }>;
  searchParams: Promise<{ notice?: string | string[] }>;
}

const DATE_FORMAT = new Intl.DateTimeFormat("en", {
  dateStyle: "long",
  timeZone: "UTC",
});

function detailNotice(value: string | string[] | undefined): string | null {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (candidate === "created") {
    return "Project created. You can now configure its name.";
  }
  if (candidate === "restored") {
    return "Project restored to your active workspace.";
  }
  return null;
}

export default async function ProjectPage({ params, searchParams }: ProjectPageProps) {
  const [{ projectId }, query] = await Promise.all([params, searchParams]);

  let project: Project | null = null;
  let loadError: unknown = null;
  try {
    project = await getProject(projectId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    loadError = error;
  }

  if (loadError || !project) {
    return (
      <ApiErrorState
        message={publicErrorMessage(loadError)}
        retryHref={`/projects/${encodeURIComponent(projectId)}`}
        reference={errorReference(loadError)}
      />
    );
  }

  const notice = detailNotice(query.notice);
  const audioCapabilityPromise = getAudioCapability().catch(() => null);
  const videoCapabilityPromise = getVideoCapability().catch(() => null);
  let conversations: Conversation[] = [];
  let history: History | null = null;
  let chatError = "";
  let answerMode: AnswerMode = "unavailable";
  let retrievalMode: RetrievalMode = "unavailable";
  try {
    ({ answerMode, retrievalMode } = await getRuntimeConfiguration());
    conversations = await listConversations(project.id);
    if (conversations[0]) history = await getHistory(project.id, conversations[0].id);
  } catch (error) { chatError = publicErrorMessage(error); }
  let sources: SourceItem[] = [];
  let playlistItems: PlaylistItem[] = [];
  let sourceError = "";
  try {
    const inventory = await listSourceInventory(project.id);
    sources = inventory.items;
    playlistItems = inventory.playlist_items;
  } catch (error) {
    sourceError = publicErrorMessage(error);
  }
  const audioCapability = await audioCapabilityPromise;
  const videoCapability = await videoCapabilityPromise;

  return (
    <div className="stack stack--large">
      <nav aria-label="Breadcrumb">
        <ol className="breadcrumbs">
          <li>
            <Link href="/projects">Projects</Link>
          </li>
          <li aria-current="page">{project.title}</li>
        </ol>
      </nav>

      {notice ? <Notice>{notice}</Notice> : null}

      <header className="project-header">
        <div>
          <p className="eyebrow">Project workspace</p>
          <h1>{project.title}</h1>
          <p className="project-card__meta">Created {DATE_FORMAT.format(new Date(project.created_at))}</p>
        </div>
        <span
          className={`status-badge status-badge--${project.status}`}
          aria-label={`Status: ${project.status}`}
        >
          {project.status === "active" ? "Active" : "Archived"}
        </span>
      </header>

      <div className="detail-grid">
        <ProjectEvidenceWorkspace projectId={project.id} initialSources={sources} initialPlaylistItems={playlistItems}
          initialConversations={conversations} initialHistory={history} archived={project.status === "archived"}
          chatError={chatError} sourceError={sourceError} answerMode={answerMode} retrievalMode={retrievalMode}
          audioCapability={audioCapability} videoCapability={videoCapability} />

        <section className="panel" aria-labelledby="settings-heading">
          <p className="eyebrow">Project settings</p>
          <h2 id="settings-heading">Name</h2>
          <ProjectRenameForm key={project.id} projectId={project.id} title={project.title} />
        </section>

        <section className="panel panel--wide" aria-labelledby="lifecycle-heading">
          <p className="eyebrow">Project lifecycle</p>
          <h2 id="lifecycle-heading">
            {project.status === "active" ? "Archive or delete" : "Restore or delete"}
          </h2>
          <ProjectLifecycleControls
            projectId={project.id}
            projectTitle={project.title}
            status={project.status}
          />
        </section>
      </div>
    </div>
  );
}
