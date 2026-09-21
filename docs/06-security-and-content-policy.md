# Security and content policy baseline

This document records architectural constraints, not legal advice. Obtain qualified legal review before a public launch that processes third-party platform content.

## YouTube constraint

Do not assume that a public YouTube URL grants permission to download, transcribe, extract frames from, or retain the audiovisual work.

Relevant official documentation:

- The official captions download API requires the caller to have permission to edit the video: <https://developers.google.com/youtube/v3/docs/captions/download>
- YouTube API developer policies restrict downloading, importing, backing up, caching, or storing audiovisual content without prior written approval: <https://developers.google.com/youtube/terms/developer-policies>
- Playlist metadata can be enumerated through `playlistItems.list`: <https://developers.google.com/youtube/v3/docs/playlistItems/list>

## Proposed supported ingestion modes

- user uploads a transcript or subtitle file;
- user uploads media they own or are authorized to process;
- authenticated creator processes their own content;
- content has a verified license compatible with the intended processing;
- an approved provider supplies a compliant transcript/media-processing path.

For a public URL without a supported path, import metadata and explain what the user must provide. Do not silently fall back to an unofficial downloader.

Record on each source:

- authorization mode;
- asserted owner/license status;
- provider and canonical ID;
- retention class;
- deletion policy;
- whether original media/frame retention is permitted.

## Threat model

### Cross-tenant access

Risk: a user retrieves another user's sources, chat, objects, or vectors.

Controls:

- tenant/project filters in every repository method;
- authorization at API and job execution time;
- PostgreSQL RLS as defense in depth;
- object-key isolation and short-lived signed URLs;
- negative isolation tests;
- citation ownership validation.

### SSRF and malicious sources

Risk: a supplied URL reaches internal or cloud metadata services.

Controls:

- parse supported provider URLs into canonical IDs;
- allowlist hostnames and schemes;
- reject redirects outside the allowlist;
- do not implement a generic fetch-URL endpoint;
- separate metadata fetchers from internal networks;
- set strict time and size limits.

### Prompt injection

Risk: transcript/document text instructs the model to ignore application policy or expose information.

Controls:

- treat retrieved content as quoted evidence, not instructions;
- keep tools and secrets unavailable to the answer generator;
- use structured context boundaries and citation IDs;
- authorize every tool call independently;
- test known injection patterns;
- prevent one source from altering project/system policy.

### Malicious uploaded files

Risk: parser exploits, decompression bombs, oversized files, or embedded active content.

Controls:

- size/type/count limits before processing;
- MIME inspection rather than filename trust;
- archive depth and expanded-size limits;
- isolated parsing workers;
- antivirus/malware scanning where appropriate;
- never render active uploaded HTML directly.

### Untrusted code execution

Risk: learner code escapes, consumes resources, scans networks, steals secrets, or affects other runs.

Controls:

- dedicated runner on separate infrastructure;
- one ephemeral sandbox per run;
- gVisor, microVM, or equivalent isolation beyond ordinary containers;
- no network by default;
- non-root user and no privilege escalation;
- read-only base image and isolated temporary workspace;
- drop Linux capabilities;
- seccomp/AppArmor/SELinux as applicable;
- CPU, memory, disk, PID, process, output, and wall-clock limits;
- no host, Docker socket, credential, or production-data mounts;
- destroy the environment after the run;
- safe truncation/redaction of returned logs.

Docker references:

- Rootless mode: <https://docs.docker.com/engine/security/rootless/>
- Seccomp profiles: <https://docs.docker.com/engine/security/seccomp/>
- gVisor architecture: <https://gvisor.dev/docs/architecture_guide/intro/>

### Secrets and provider credentials

- use a secret manager in production;
- use narrowly scoped service identities;
- never bake secrets into images;
- never provide provider credentials to sandboxes;
- redact request/response logs;
- rotate compromised keys and preserve audit evidence.

### Denial of service and cost abuse

- duration and file-size limits;
- bounded playlist size;
- per-tenant job concurrency;
- model token and vision-frame budgets;
- preflight cost estimates;
- cancellation and spend caps;
- deduplicated source processing;
- backpressure and dead-letter handling.

## Retention and deletion

Define retention classes for:

- source metadata;
- uploaded transcript/media;
- extracted frames;
- OCR/descriptions;
- embeddings;
- chat;
- submissions;
- execution logs;
- model-provider logs.

Project deletion must cover PostgreSQL rows, embeddings, objects, caches, queued jobs, and provider-held artifacts where APIs permit. Backups require a documented expiry model.

## Docker supply-chain baseline

- minimal pinned base images;
- image digests for grading environments;
- non-root `USER` declarations;
- multi-stage builds;
- dependency and image vulnerability scanning;
- SBOM generation;
- signed images where practical;
- no privileged workloads;
- no Docker socket mounts;
- automated rebuilds for patched base images.

