# Releasing a new version of SeaVision to PyPi

These instructions describe the standard process for releasing a new version of SeaVision.

1. Work on a release-prep branch, not directly on Main.

2. Make the release changes on that branch, including updating the version in:
   - pyproject.toml
   - seavision/__init__.py

3. Commit and push the branch.
```bash
git add .
git commit -m "Prepare release X.Y.Z"
git push
```

Wait for CI to pass on the branch.


4. Open a pull request and merge it into Main.

Wait for CI to pass again on Main after the merge.

5. Update your local copy of Main and confirm it is clean.
```
git checkout Main
git pull origin Main
git status -sb
```

6. Create a tag from the merged Main commit and push it.
```
git tag -a vX.Y.Z -m "SeaVision X.Y.Z"
git push origin vX.Y.Z
```

*NB: Using final release tage (vX.Y.Z) will releas to PyPi, prerelease tags (vX.Y.Za1) release to test PyPi.*

7. Pushing the tag triggers the release workflow automatically.
