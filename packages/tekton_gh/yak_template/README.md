# Yak template

`manifest.yml` and `icon.png` for the Rhino package (Yak). `invoke yakerize`
copies both into `dist/yak_package/`, fills in the version, adds the built
`.ghuser` files plus README and LICENSE, and runs `yak build`. See
docs/RELEASE.md.

`icon.png` is a placeholder (the Tekton Display icon at 96 px) until there is
a package logo.
