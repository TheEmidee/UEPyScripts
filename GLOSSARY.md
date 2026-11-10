# UEPyScripts

Build, CI and binary-distribution tooling for Unreal Engine projects that ship with a source-built (native) engine.

## Workspace

**Workspace**:
The project, its config and its engine, resolved together from one uproject. The single starting point for every command.
_Avoid_: context, session

**Native project**:
A project whose `.uproject` sits in a folder next to the engine's `Engine` folder, in the same source tree, with an empty `EngineAssociation`. The engine is that tree's root. Being native is a property of the folder layout, never a choice a command makes.
_Avoid_: source build (when you mean the layout)

**Engine association**:
The `EngineAssociation` value of a `.uproject`: empty for a Native project, a launcher version such as `5.4`, the name of a registered build, or a path to an engine folder.

**Engine locator**:
Finds the engine root folder a project needs from its Engine association, trying in order: the Native project layout, a registered build, a launcher install, the association as a path, then `NODE_UE_ROOT`.
_Avoid_: engine resolver

**Engine tool**:
A program inside the engine that a command launches: UAT (`RunUAT.bat`), UBT (`UnrealBuildTool.exe`), `Build.bat`, or the editor (`UnrealEditor.exe`). It may not exist yet in a freshly cloned engine.

**Project config**:
The `.ini` files in the project's `Config/PyScripts` folder, merged in file-name order. A missing folder is an empty Project config.
_Avoid_: config.ini (it may be several files), settings file

**Config section**:
One `[Section]` of the Project config, read as a single typed value the first time a command asks for it. Missing or malformed keys are all reported together.
_Avoid_: config entry, settings group

## BuildGraph

**BuildGraph command**:
One UAT BuildGraph invocation: the script, one target or one Single node, the project, script folders, properties, build-machine and shared-storage flags, and extra arguments that override generated ones with the same key.
_Avoid_: buildgraph args, UAT arguments (when you mean the whole invocation)

**Single node**:
Running one node of a BuildGraph graph on its own, sharing its inputs and outputs with other agents through the Shared storage. Only CI (`ue-ci-run-buildgraph`) runs Single nodes, one per task.
_Avoid_: task (when you mean the BuildGraph node)

**Build tag**:
The name CI gives one build, such as `jenkins-42`. Every Single node of that build shares it.
_Avoid_: build number, version (that is a published commit)

**Shared storage**:
The folder where the Single nodes of one build exchange their outputs: `[Jenkins] BuildgraphSharedStoragePath / <Build tag>`, with one subfolder per Single node. Deleted by `ue-ci-cleanup` once the build is over.
_Avoid_: shared storage dir (when you mean the whole build's folder), NAS

## Binary publishing (UGS)

**Version**:
A commit SHA whose engine and game binaries have been published. A Version exists exactly when its Manifest exists in the Publish store.
_Avoid_: build, release, publish (as a noun)

**Manifest**:
The complete list of tracked files at one Version, each mapped to the content hash of that file.
_Avoid_: file list, state

**Tracked files**:
The files of the engine tree that make up a Version: binaries and build metadata matched by folder and extension, plus explicit glob patterns. Ignored folders and hot-reload patch files are left out. PDBs are never Tracked files; they go to the symbol store instead.
_Avoid_: sync files, published files

**Blob**:
The stored content of one file, identified by its content hash. Identical files across Versions and branches share one Blob.
_Avoid_: object, chunk, archive

**Hash cache**:
Per-file fingerprints recorded at a commit so the next publish can skip re-hashing unchanged files. It is a speed-up only; losing it never affects correctness.

**Publish store**:
The Manifests, Blobs, Hash caches and symbol-store manifest kept in the bucket, treated as one thing.
_Avoid_: bucket (when you mean its contents), binary cache

**Sync**:
Making the local engine tree match one Version's Manifest: downloading the files whose hash differs from the Sync state and deleting the ones no longer tracked. The target is the nearest Version in HEAD's ancestry, or the latest Version when none is (history was rewritten).
_Avoid_: pull (that is the command), download (that is one step)

**Sync state**:
The Version and Manifest the last completed Sync wrote, kept at the engine root. Local files are trusted to match it and are never hashed. It is only written once every file of a Sync has been written, and an unreadable one counts as no previous Sync.
_Avoid_: local state, sync-state.json (that is the file)
