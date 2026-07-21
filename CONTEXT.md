# AI Studio Void — Domain glossary

The shared language of the app. Glossary only — no implementation details (those live in specs + ADRs).

## Presets — two distinct objects (never conflated)

- **Style** *(a.k.a. Profile)* — a **reusable, prompt-optional** preset. It carries a negative prompt, an optional positive-prompt **template** (which may contain a `{prompt}` hole), default generation parameters, and optionally a model. A Style is applied *to* any subject; it is not tied to one image. Applying a Style is **explicit and idempotent** and must never silently overwrite or blank a field the user edited by hand.

- **Recipe** *(a.k.a. Shot)* — a **re-runnable snapshot of one exact generation**: the exact prompt, negative prompt, seed, model, provider, and the full resolved parameters. A Recipe reproduces *a specific image*. Because it pins seed/model/provider, a Recipe is **provider-specific** — reusing it on another provider maps the known params and degrades unknown ones, rather than failing.

- **App defaults** — the single unnamed parameter set the app persists as the current working values (the fallback when no Style or Recipe is applied). This is a **third, separate layer** — neither a Style nor a Recipe.

> The distinction exists to prevent the collision every mature tool hit: "styles that also save my params" vs "presets that reset the params I hand-edited" are two faces of one over-loaded object. Keeping Style and Recipe separate resolves both.

## Library

- **Library** — the browsable collection of every image the app knows about, across the configured folders. Distinct from any one folder on disk.

- **Library Index** — the local **fast source of truth** for the Library: one record per image plus its tags, queried directly so browsing never re-reads the underlying (often network) storage. The images and their on-disk/embedded metadata are the durable copy; the Index is the fast copy. The two are kept in sync but are not the same thing.

- **Auto-tag** — a tag the app derives from a generation's own metadata (provider, model, seed, dimensions, date, has-negative-prompt). The user never types these.

- **Manual tag** — a tag the user types to organise their own work. Lives alongside auto-tags.

- **Output directory** — the folder new generations are written to. It is always a member of the Library's scan set, so a generated image is findable the moment it is created. (Historically it pointed outside the scan set, which is why generations were unfindable.)

## Providers & content

- **Provider** — an upstream generation service (fal, Novita, Together, Runware, Replicate, OpenAI, NVIDIA, Gemini, AGNES, Ideogram, cliproxy). Each has its own model catalog, parameter vocabulary, and content policy.

- **Content capability** — a per-**model**, evidence-backed grade of whether that model actually produces permissive/NSFW output (not a per-provider assumption). Drives the Content Mode filter.
