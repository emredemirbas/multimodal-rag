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

The internal curriculum provider exposes only a local JSON completion interface,
with fixed model/options and explicit digest/engine pins. It disables proxies,
redirects, tools, thinking and cloud fallback; only local tags/show/version/chat
endpoints are used. Schema `$ref` links must point inside the supplied schema. Bound request/body/
response bytes, reject duplicate/non-finite JSON and reject incomplete or late
output. A completed JSON object is not evidence support or assignment-schema
approval: the internal workflow parses its application contract and binds it
against the authorized context before publication. Exact quotes must occur in
their named source slice; every slice needs an explicit model coverage status.
This verifies literal grounding/relationships, not semantic entailment. Unsupported
output cannot waive deterministic validation; only one bounded draft revision is
allowed. Public/default processor registration stays closed pending native review.
LangGraph hosted tracing is explicitly disabled inside construction/invocation
without changing owner environment variables; no library checkpoint store receives
project text. Logs contain only safe identifiers and fixed rejection codes.
True external-topic/document permissions still fail before inference in the current
internal graph. Step 5a adds an independent approved-capture API, not document
binding or model permission. The owner confirmed opt-in external topics and
explicit approval for each official document. Its fixed catalog policy, exact
fingerprint and retrieve-and-retain consent are saved per context/approving actor.
Only that actor can issue the separate capture command. All DNS answers must be
public; sockets pin a validated numeric address with verified original-host TLS.
No redirect/proxy/cookie/authentication or arbitrary URL is supported. A stripped-
environment trusted child has independent and parent-enforced wall deadlines,
CPU/memory/output limits and bounded inert HTML extraction. Raw HTML is discarded;
stored text/excerpts stay untrusted. Failure replay never silently refetches.
Current membership/context/policy/token/clock checks fence all adoption, and
source/context/project deletion removes approvals, text and receipts. This child
executes application-owned parsing only; it is not an untrusted-code sandbox.
The 0026 draft boundary accepts only explicitly selected, captured copies in the
same saved context/project. It rechecks retained consent/policy, application-owned
exact URL and content/excerpt identities without fetching. Per-revision dependencies
remove an entire logical draft/history and receipts/result pointers if any selected
document is deleted, including older or uncited selections. Deletion confirmation
states that effect. Scoped context -> document -> draft locks and a final head
recheck prevent direct deletion from racing an orphan revision into storage.
The draft review BFF reauthorizes scope, checks copied tutorial text against the
immutable context and selected document excerpts against retained captures, and
matches replacement receipts to the submitted content and revision. Strict bounded
original JSON and same-origin writes apply; browser text stays literal and is not
persisted in local/session storage. Conflict handling never silently overwrites a
newer revision; uncertain saves keep their original command and body. Explicit
deletion hides text pending reconciliation and fences late responses. The graph's
external flags and public generation remain closed. See the Sprint 5 plan for
precise resource caps and outstanding activation work.

### Malicious uploaded files

Risk: parser exploits, decompression bombs, oversized files, or embedded active content.

Controls:

- size/type/count limits before processing;
- MIME inspection rather than filename trust;
- archive depth and expanded-size limits;
- isolated parsing workers;
- antivirus/malware scanning where appropriate;
- never render active uploaded HTML directly.

The experimental WAV boundary additionally authenticates/checks the operator flag
before body consumption, bounds actual wire bytes and unfinished-read time before
multipart parsing, and uses a separate same-origin BFF without exposing its token.
It requires explicit rights/language/temporary-retention fields and rejects unknown
or duplicate fields. The API validates RIFF/PCM structure without a native decoder;
only bounded PCM reaches the existing credential-free isolated local ASR service.
Capability is configuration, not model readiness. Originals expire for processing
after one hour and are physically deleted through observable retryable cleanup;
expiry or browser abort must not be represented as confirmed deletion/cancellation.
No arbitrary URL fetch, cloud fallback or broader media retention is authorized
(ADRs 0018–0020).

The separately delegated MP4/selected-frame scope (ADR 0021, 2026-10-26) begins
with an explicit stateless no-network FFmpeg/Tesseract container, not a product
upload endpoint. Native children inherit socket denial and receive no app
credentials/mounts; temporary originals/intermediates live only in bounded tmpfs.
Fixed MOV/H.264/protocol options and native resource/time/output limits supplement
kernel/container restrictions. Future durable originals need terminal retirement,
<=one-hour processing eligibility and independently confirmed cleanup; permitted
selected frames/OCR may remain only until complete source/project deletion.
Capability stays closed until authorization/lifecycle/UI/evidence are delivered.

The private visual HTTP continuation retains that boundary: only a prebound
internal listener survives inherited socket/connect denial, with no public ports,
app network/credentials or mounts. A four-connection/one-extraction limit, absolute
10-second header/body deadline, bounded native children, five-second response write
timeout and finite JSON/image bounds constrain work. The client pins identities,
checks actual input/frame digests and PNG CRC/bounded decoded geometry, rejects
redirects/proxies and has a 145-second absolute socket deadline (three seconds for
readiness, plus bounded connection setup). Request framing rejects duplicate
length/type/profile/digest headers, encodings, credential/project headers and URL
input. Logs contain fixed routes/status/count/timing only. This is an opt-in local
parser protocol, not an Internet-facing server, authorization layer or security
certification; scoped durable video jobs/deletion remain mandatory follow-up.

The subsequent visual checkpoint store is trusted-worker code excluded from the
native parser image. Begin/save/load recheck both scopes, source/job/generation,
initiating actor membership, exact token, live wall-clock lease and fixed one-hour
job-creation eligibility. Membership is key-share locked until transaction end;
eligibility loss before commit rolls back every staged frame. Input/profile/rights
drift and incomplete/corrupt PNG/OCR manifests fail closed. Complete selected-frame
snapshots are bounded private PostgreSQL data, never retrieval/public evidence;
source/project deletion cascades through bytes/text. Derived staging retention is
separate from processing eligibility and future raw physical cleanup. No raw input
is stored or filename/media/OCR/input fingerprint logged by this DB component.

ADR 0022 connects that store to a private trusted visual coordinator. A committed
unique-prefix orphan reservation precedes PUT; source/job/outbox/input adoption
rechecks initiating membership and project status, locking membership through commit.
Only that worker joins both networks, never exposing app credentials to the native
service. Original reads check generated scoped key, actor, digest/byte count and
eligibility before and after storage. Cached preparation revalidates the raw record
without fetching it. Fixed one-hour eligibility cannot be extended by retry.
Every terminal path and scheduler expiry/revocation pass creates a scoped raw
cleanup ticket; physical deletion is separately verified and failures remain
observable/retryable, not reported as deleted. Prepared PNG/OCR stays private until
full source/project deletion. No public MP4 route/form or final evidence is enabled.

ADR 0023 adds derived PNG adoption, still without product MP4 upload/indexing.
Each candidate gets a separately committed unique cleanup prefix before PUT;
post-PUT membership is locked through commit, and actual wall-clock lease/source/
generation checks prevent stale adoption. One PNG per delivery bounds I/O;
continuations do not consume a failure attempt. Original deletion/expiry does not
prevent use of already permitted prepared derivatives. Only a complete verified
manifest receives the gallery publication marker. Failed/cancelled partial objects
remain private until retry or complete source/project cleanup; old orphan tickets
cannot delete newer accepted candidates.

Read APIs enforce both scopes and membership, validate retained manifest/PNG hashes,
geometry and size, and reauthorize after object I/O. Browser proxy uses server-only
credentials, an eight-second request deadline, actual <=600,000-byte streaming cap,
PNG-only framing, no redirects and no-store/nosniff/same-origin headers on all
outcomes. Cross-site image embedding is rejected. Render OCR literally, label it
unreviewed and preserve image-error/text-only inspection. A gallery is not indexed
evidence, an original-video download, human review or OCR quality approval.

ADR 0024 subsequently indexes only already permitted retained OCR. Internal
commands verify a complete published manifest, original initiating actor/rights
and scope; jobs pin gallery, parser and embedding space. Every batch/promotion
checks exact source/job/generation/token/actor, key-share locks membership and
rechecks actual wall-clock lease before commit. Stored text/frame/vector digests
are revalidated; scoped FKs prevent attaching another source's frame/gallery.
Private chunks are never retrieved or exposed; partial/failed replacement cannot
remove old active evidence. Indexing does not extend raw eligibility, fetch an
original/object, invoke native tools or select a new provider. Complete deletion
cascades chunks/evidence/version origin and derived chat, with existing PNG cleanup.

Literal unreviewed OCR remains untrusted context, never instructions or verified
code. Text-only answer policy explicitly forbids unseen visual/speech claims;
point PTS is not a visible-duration interval. Version-pinned origin/frame references
are checked before citations/history/evidence are returned, not inferred from
mutable metadata. Browser links use existing protected gallery/image boundaries;
no raw/signed public object URL or fake player. Public MP4 upload stays closed.

ADR 0026's subsequent experimental boundary is separately gated by
`VIDEO_UPLOAD_ENABLED=false`; it authorizes no wider codec/size/language/retention
or downloader/provider. Explicit standalone rights/selected-frame retention
consent precedes existing atomic jobs. API authenticates/gates before reads; BFF
checks same-origin/UUID/configuration first and never forwards client credentials.
Count actual wire bytes (100 MB +16 KiB) before multipart parsing, bound stalled
reads to 30 seconds and reject excessive BFF markers/unknown or duplicate fields.
Each process admits only one video delivery and releases its slot on every exit.
The API's bounded 256 MiB tmpfs fits the spooled file; it is not durable storage or
a change to other upload limits. No native codec is loaded into API/BFF workers.

The BFF verifies source project/type/rights/language/lifecycle and original job
before emitting only receipt IDs. Delivery interruption is not job cancellation;
preserve an uncertain unchanged draft/key. Typed raw lifecycle comes from scoped
input/cleanup rows and keeps expiry distinct from confirmed deletion. Failed
cleanup retry remains scoped to its original initiator. Existing protected frame
reads, unreviewed OCR policy and complete object/checkpoint/chat deletion remain
authoritative. No audio transcription, player, playlist mapping, scene/description
quality or default enablement is implied. See `sprint4/video-upload-plan.md`.

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
