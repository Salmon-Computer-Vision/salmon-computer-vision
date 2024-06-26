Place TensorRT engine file weights in the `config` folder.

Create an `.env` file here with the following:
```
IMAGE_REPO_HOST=<host>
DRIVE=/media
WEIGHTS=/app/config/<salmoncount_weights>.engine
```

!! Make sure your drive folder is named `hdd` and is the next subdir after your `${DRIVE}` dir.

If you have any private docker repos, you may need to install
the following to login with docker:
```bash
sudo apt install gnupg2 pass
```

Then, you should be able to login:
```bash
docker login
```
