# /bin/zsh
# Re-tag the commit history with tags to provide checkpoints for the tutorial
git tag | xargs git tag -d
git checkout main
git tag fidesops-demo
git checkout HEAD^1
git tag fidesops-start
git checkout HEAD^1
git tag fidesctl-demo
git checkout HEAD^1
git tag fidesctl-add-google-analytics
git checkout HEAD^1
git tag fidesctl-manifests
git checkout HEAD^1
git tag fidesctl-start
git checkout HEAD^1
git tag tutorial-start
git checkout main
echo "Re-tagged git history:"
git log --oneline
echo "Use git push -f --tags when ready!"
