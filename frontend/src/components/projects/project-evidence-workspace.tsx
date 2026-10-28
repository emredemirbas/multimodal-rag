"use client";

import { useState } from "react";

import { ChatWorkspace } from "@/components/chat/chat-workspace";
import { SourcesWorkspace } from "@/components/sources/sources-workspace";
import type { AudioCapability } from "@/lib/api/audio-contracts";
import type { AnswerMode, Conversation, History, RetrievalMode } from "@/lib/api/chat-contracts";
import type { PlaylistItem, SourceItem } from "@/lib/api/source-contracts";
import type { VideoCapability } from "@/lib/api/video-contracts";

interface Props {
  projectId: string;
  initialSources: SourceItem[];
  initialPlaylistItems: PlaylistItem[];
  initialConversations: Conversation[];
  initialHistory: History | null;
  archived: boolean;
  chatError: string;
  sourceError: string;
  answerMode: AnswerMode;
  retrievalMode: RetrievalMode;
  audioCapability: AudioCapability | null;
  videoCapability: VideoCapability | null;
}

function ProjectEvidenceScope(props: Props) {
  const [sources, setSources] = useState(props.initialSources);

  return <>
    <section className="panel panel--wide" aria-labelledby="chat-heading">
      <p className="eyebrow">Ask and inspect</p>
      <h2 id="chat-heading">Chat with tutorial evidence</h2>
      <ChatWorkspace projectId={props.projectId} sources={sources}
        initialConversations={props.initialConversations} initialHistory={props.initialHistory}
        archived={props.archived} initialError={props.chatError}
        answerMode={props.answerMode} retrievalMode={props.retrievalMode} />
    </section>
    <section className="panel panel--wide" aria-labelledby="workspace-heading">
      <p className="eyebrow">Learning material</p>
      <h2 id="workspace-heading">Source management</h2>
      <SourcesWorkspace projectId={props.projectId} initialSources={props.initialSources}
        initialPlaylistItems={props.initialPlaylistItems} archived={props.archived}
        initialError={props.sourceError} audioCapability={props.audioCapability}
        videoCapability={props.videoCapability} onSourcesChanged={setSources} />
    </section>
  </>;
}

export function ProjectEvidenceWorkspace(props: Props) {
  return <ProjectEvidenceScope key={props.projectId} {...props} />;
}
