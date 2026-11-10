# UEPyScripts

Build, CI and binary-distribution tooling for Unreal Engine projects that ship with a source-built (native) engine.

## Workspace

**Workspace**:
The project, its config and its engine, resolved together from one uproject. The single starting point for every command.
_Avoid_: context, session

**Native project**:
A project whose `.uproject` sits in a folder next to the engine's `Engine` folder, in the same source tree, with an empty `EngineAssociation`. The engine is that tree's root. Being native is a property of the folder layout, never a choice a command makes.
_Avoid_: source build (when you mean the layout)

## Binary publishing (UGS)

**Version**:
A commit SHA whose engine and game binaries have been published. A Version exists exactly when its Manifest exists in the Publish store.
_Avoid_: build, release, publish (as a noun)

**Manifest**:
The complete list of tracked files at one Version, each mapped to the content hash of that file.
_Avoid_: file list, state

**Blob**:
The stored content of one file, identified by its content hash. Identical files across Versions and branches share one Blob.
_Avoid_: object, chunk, archive

**Hash cache**:
Per-file fingerprints recorded at a commit so the next publish can skip re-hashing unchanged files. It is a speed-up only; losing it never affects correctness.

**Publish store**:
The Manifests, Blobs, Hash caches and symbol-store manifest kept in the bucket, treated as one thing.
_Avoid_: bucket (when you mean its contents), binary cache
