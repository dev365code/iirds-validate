# Draft: request to the iiRDS Consortium

**Status: not sent.** This is a draft for the maintainer to review, adapt and
send. Do not send it on anyone's behalf without asking them first.

**Suggested recipient:** `comment.iirds@tekom.de` — the address the
specification itself gives for comments. The `iirds-consortium/models` issue
tracker is a reasonable public alternative, and arguably the better one: it
puts the question where the files actually live and lets other implementers
add their voice.

**What we are asking for:** a permissive licence on the machine-readable schema
files only. We are *not* asking for anything about the specification text.

**What happens if the answer is no:** nothing breaks. CC BY-ND already permits
verbatim redistribution, which is what the project does today. The request is
about removing friction for downstream packagers, not about unblocking
ourselves.

---

## Draft

Subject: Licensing of the iiRDS RDF schema files for use in open-source tooling

Dear iiRDS Consortium,

I maintain `iirds-validate`, an open-source command-line validator for iiRDS
packages. It exists because iiRDS is deployed in manufacturing environments
where the existing browser-based validation tool cannot be used: those networks
have no route to the internet, and validation needs to run unattended as part of
a build rather than by hand in a browser tab.

To work without network access, the tool bundles the five iiRDS RDF schema files
verbatim, with their copyright headers intact, under the terms of CC BY-ND 4.0
Section 2(a)(1). Their checksums are published and verified at install time so
that anyone can confirm nothing has been altered.

I am writing about one consequence of that.

**The request.** Would the Consortium consider releasing the machine-readable
schema files — `iirds-core.rdf`, `iirds-machinery.rdf`, `iirds-software.rdf`,
`iirds-handover.rdf` and `iirds-skos.rdf` — under a permissive licence such as
CC BY 4.0 or Apache-2.0, while leaving the specification text under CC BY-ND?

**Why it matters.** CC BY-ND is not an OSI-approved licence and is not DFSG-free.
Redistributing the schema is legal, but any package containing it cannot be
accepted into Debian, Fedora or several other distributions, and a number of
corporate open-source review processes reject NoDerivatives content on sight,
independently of what the content is. The practical effect is that iiRDS tooling
is harder to distribute than iiRDS adoption would benefit from.

The distinction between the two kinds of material seems to be the point. The
NoDerivatives condition protects the specification: nobody should be able to
publish an altered document and call it iiRDS. A schema file is different in
kind. It is not prose to be preserved; it is data that every implementation has
to load, transform between serialisations, subset for testing, and embed. Those
are exactly the operations the licence discourages, and none of them threaten
the integrity of the standard.

**Two things that suggest this is already the intended direction.** The
Consortium's own `iirds-consortium/dita-ot-plugin` repository is released under
Apache-2.0. And `iirds-consortium/models`, which publishes four of these same
RDF files, currently carries no licence file at all — so the identical bytes are
CC BY-ND when obtained from iirds.org and unlicensed when obtained from GitHub.
Whichever way the Consortium prefers to resolve that, resolving it would help
implementers considerably.

**If a licence change is not possible,** a short written statement confirming
that verbatim redistribution of the schema files inside software distributions
is permitted, with attribution, would still be valuable. It is what the licence
already says; having it stated plainly would let downstream packagers stop
deriving it themselves.

I would also welcome correction on two smaller points:

- whether the Consortium considers descriptive use of the name "iiRDS" in a
  package name such as `iirds-validate` acceptable, and what wording it would
  prefer for the disclaimer of affiliation;
- whether there is interest in the project contributing its rule set back. The
  validation rules are currently maintained inside one vendor's application and
  are not available in a machine-readable, language-neutral form, which
  `iirds-consortium/models` issue #24 has been asking for since April 2025.

The project is at <URL>, and I am happy to make any changes that would make the
Consortium comfortable with how its material is used.

With thanks for the standard and for the work behind it,

<name>
<affiliation, if any>

---

## Notes for the sender

- Fill in `<URL>`, `<name>`, `<affiliation>`. Leave the affiliation out if this
  is personal work — see the last section of `licensing.md`.
- Send it after the repository is public. A request that points at nothing is
  harder to say yes to.
- Jan Oevermann appears both as an author of the 1.3 specification and as the
  only contributor to `iirds-consortium/models`. If the question stalls on the
  mailing address, that repository's issue tracker is where it will actually be
  read.
- Do not describe the project as endorsed, certified, or official at any point,
  before or after a reply.
