# Local development

`docker-compose up` runs this api with a local postgres db for data persistence. Then access from `http://localhost:8000` on a web browser. `docker-compose.yml` defines the local environment.

# Deploying on Heroku
You must have [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) and the [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli#download-and-install) installed.

To create an app from the setup section defined in heroku.yml manifest, install the heroku-manifest plugin from the beta update channel:
```
heroku update beta
heroku plugins:install @heroku-cli/plugin-manifest
```
You can switch back to the stable update stream and remove the plugin at any time:
```
heroku update stable
heroku plugins:remove manifest
```
Then create your app using the --manifest flag. The stack of the app will automatically be set to container:
```
heroku create your-app-name --manifest --region eu
```
Push the code to deploy:
```
heroku git:remote -a your-app-name
git push heroku main
```
