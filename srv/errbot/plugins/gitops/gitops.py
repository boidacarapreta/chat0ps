from errbot import BotPlugin, botcmd, webhook, ONLINE, AWAY
from bottle import abort
from pymongo import MongoClient
from requests import head, codes

class GitOps(BotPlugin):
    """Gitops integration: PubSub via Webhook"""


    def check_mongo(self):
        client = MongoClient(host='mongodb')
        try:
            response = client.local.command("ping")
        except:
            self.change_presence(AWAY, "MongoDB is down!")
        else:
            self.change_presence(ONLINE, "All services up and running.")


    def activate(self):
        super().activate()
        self.start_poller(10, self.check_mongo)


    @webhook(raw=True)
    def publish(self, request):
        """Webhook for git pushes"""
        # For now, just GitHub webhooks are accepted.
        # Soon others providers, like GitLab, will be available.
        if request.get_header("user-agent").split("/")[0] == "GitHub-Hookshot":
            # It is a ping or a push event?
            if request.get_header("X-GitHub-Event") == "ping":
                return None
            else:
                payload = request.json
                repository = payload["repository"]["url"]
                branch = payload["ref"].split("/")[-1]
                pusher = payload["pusher"]["email"]
                diff = payload["compare"]
        else:
            abort(400, "Bad Request")
        # Get subscribers' list
        collection = MongoClient(host='mongodb').chat0ps.subscriptions
        document = {"repository": repository}
        message = "GitHub notification: " + pusher + " pushed to `"
        message += branch + "` in `""" + repository + "`."
        message += " You can look the diff in: " + payload["compare"] + "."
        subscribers = collection.find_one(document)
        if subscribers is None:
            self.warn_admins("Warning: webhook in " + repository + " with no subscriber.")
        else:
            for subscriber in subscribers["subscribers"]:
                self.send(self.build_identifier(subscriber), message)


    def validURL(self, args):
        if len(args) == 0:
            return None
        url = args[0]
        try:
            response = head(url, allow_redirects=True)
        except:
            return None
        if response.status_code == codes.ok:
            return url
        else:
            return None


    @botcmd(split_args_with=None)
    def subscribe(self, msg, args):
        """
        Subscribe to repository notifications.
        It takes only one mandatory argument: the respository URL (must be public HTTP or HTTPS).
        """
        # Validate arguments: only the first in URL valid format
        url = self.validURL(args)
        if url:
            collection = MongoClient(host='mongodb').chat0ps.subscriptions
            # First check: if repository exists
            repository = {"repository": url}
            if collection.count_documents(repository) >= 1:
                # Second check: if user is subscribed to this repository
                subscription = {"repository": url, "subscribers": msg.frm.person}
                subscriptions = collection.count_documents(subscription)
                if subscriptions >= 1:
                    # No need to update collection.
                    yield "Repository already subscribed."
                else:
                    # Add user to subscribers list
                    collection.update(repository, {"$push": {"subscribers": msg.frm.person}})
                    yield "Done. You may now set repository webhook to: http://35.198.17.35/publish"
            else:
                # If the repository doesn't exists, it's time to create
                # and subscribe the user to it in a single command.
                # Note a little difference here: "subscribers" ust be a list.
                subscription = {"repository": url, "subscribers": [msg.frm.person]}
                collection.insert_one(subscription)
                yield "Done."
        else:
            yield "Please inform a valid URL."


    @botcmd(split_args_with=None)
    def unsubscribe(self, msg, args):
        """
        Unsubscribe to repository notifications
        It takes only one mandatory argument: the repository URL.
        """
        url = self.validURL(args)
        if url:
            collection = MongoClient(host='mongodb').chat0ps.subscriptions
            # Check: if subscription exists
            repository = {"repository": url}
            document = {"repository": url, "subscribers": msg.frm.person}
            subscriptions = collection.count_documents(document)
            if subscriptions >= 1:
                collection.update(repository, {"$pop": {"subscribers": msg.frm.person}})
                yield "Done"
            else:
                yield "Sorry, you're not subscribedto this repository."
        else:
            yield "Please inform a valid URL."


    @botcmd
    def subscriptions(self, msg, args):
        """
        List all repository subscriptions.
        """
        collection = MongoClient(host='mongodb').chat0ps.subscriptions
        document = {"subscribers": msg.frm.person}
        subscriptions = collection.count_documents(document)
        # Check if there is at least one subscription
        if subscriptions >=1:
            # Yes, there is. Time to list them all.
            for subscription in collection.find(document):
                yield subscription["repository"]
        else:
            yield "Sorry, no subscribed repository."
