# Product brief

## Product statement

Build an AI learning workspace that turns programming video tutorials and playlists into searchable, citation-backed course material and practical, assessable coding assignments.

The product should help a learner move through this loop:

```text
Import material → understand it → ask questions → apply it → receive feedback → retry
```

The assessment and feedback loop is the principal differentiator. Chat supports the learning experience; it is not the whole product.

## Problem

Long-form video tutorials are useful but passive. Learners often cannot:

- locate a specific explanation later;
- connect speech with code, diagrams, or UI shown on screen;
- determine whether they can apply the material independently;
- receive a properly scoped practice project;
- obtain consistent, evidence-based feedback on their work.

## Initial user

Proposed first persona:

- an intermediate Python learner;
- studying backend/API development independently;
- following a single tutorial or a 10–20 video playlist;
- willing to complete a small coding project after learning;
- comfortable uploading a source file or using authorized/licensed material.

## Primary user journey

1. User creates a private project.
2. User adds a supported video, playlist, transcript, or media source.
3. The application asynchronously processes transcript and useful visual evidence.
4. User sees per-source progress and any actionable errors.
5. User asks questions and receives answers with video/timestamp or documentation citations.
6. The application extracts learning objectives and proposes a case study.
7. The case study identifies covered, prerequisite, and extension requirements.
8. User chooses or accepts a deadline.
9. User uploads a solution.
10. Deterministic checks run inside a hardened sandbox.
11. The application returns test results, rubric feedback, citations, and progressive hints.
12. User revises and resubmits; the project records progress and mastery evidence.

## Product principles

- **Evidence first:** claims about a tutorial link back to precise evidence.
- **Active learning:** prioritize building and feedback over passive summaries.
- **Honest scope:** clearly separate tutorial content from prerequisite and extension material.
- **Recoverable processing:** ingestion is asynchronous, observable, idempotent, and retryable.
- **Project isolation:** no retrieval, conversation, or artifact crosses project boundaries.
- **Safe execution:** untrusted code never runs in the normal API or worker environment.
- **Provider portability:** model providers sit behind application-owned interfaces.

## Initial scope

- Python backend programming tutorials
- Single videos and playlists
- Multiple sources within one isolated project
- Timestamped transcripts
- Selected frames for slides, diagrams, terminals, IDEs, and code changes
- Project-scoped hybrid RAG
- Modern streaming chat UI
- Structured coding assignments
- File/archive submissions
- Automated tests and rubric feedback
- Progress, attempts, and optional deadlines

## Explicit beta non-goals

- Arbitrary non-programming subjects
- Native mobile clients
- Cohorts, classrooms, or instructor administration
- Real-time collaboration
- Plagiarism detection
- Arbitrary web crawling
- Private YouTube account integration
- Self-hosted foundation models
- Fully autonomous assignment publication without review
- Kubernetes as a prerequisite
- Email/SMS/push reminders

## Product risks

1. Unsupported or non-compliant YouTube ingestion
2. Inconsistent assignment quality
3. Unsafe execution of learner code
4. Hallucinated or inaccurate citations
5. Version mismatch between old tutorials and current documentation
6. High cost for long playlists and frame analysis
7. Over-broad subject scope
8. Attractive chat UI masking weak learning outcomes

## Success measures

Product measures:

- percentage of projects reaching `ready`;
- time from source submission to first useful answer;
- assignment acceptance and completion rates;
- resubmission rate after feedback;
- user-reported usefulness of citations and feedback;
- cost per processed video hour and active project.

Learning measures:

- pre-task versus post-task performance;
- ability to complete a novel transfer task;
- reduction in hints required across attempts;
- time to independent successful submission.

