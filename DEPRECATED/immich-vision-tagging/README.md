# Deprecated Immich Ollama vision tagging pilot

Deprecated on 2026-07-26 after the one-day pilot.

The job sent Immich preview images to Ollama gemma3:12b and wrote the
resulting labels as hierarchical ollama/* tags. The output was not useful for
the private library because the general-purpose model produced overly vague,
safety-tuned labels for softporn imagery.

Immich's internal context extractor is preferred for this library. The
manifests in this directory are retained only as historical reference and are
outside the active immich and ollama Argo CD application paths.
