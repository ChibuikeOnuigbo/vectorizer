# Frozen training dataset snapshot

Gzipped copy of model/data/dataset.json so the recurring snapshot restores
(which delete gitignored model/data/) cannot wipe the expensive candidate
dataset (0.58s per image to rebuild). Restore with:

  python3 -c "import gzip,shutil; shutil.copyfileobj(gzip.open('model_data_snapshot/dataset.json.gz','rb'), open('model/data/dataset.json','wb'))"

Note: records reference image paths under model/data/ which must also be
regenerated; the params.npz/params.onnx in app/static/model/ are the real
deliverable and are committed after each training round.
