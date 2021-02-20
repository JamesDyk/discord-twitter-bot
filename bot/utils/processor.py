from html import unescape
import re
from discord import Webhook, RequestsWebhookAdapter, Embed
import discord
import random
import time
from datetime import datetime


COLORS = [
    0x7F0000,
    0x535900,
    0x40D9FF,
    0x8C7399,
    0xD97B6C,
    0xF2FF40,
    0x8FB6BF,
    0x502D59,
    0x66504D,
    0x89B359,
    0x00AAFF,
    0xD600E6,
    0x401100,
    0x44FF00,
    0x1A2B33,
    0xFF00AA,
    0xFF8C40,
    0x17330D,
    0x0066BF,
    0x33001B,
    0xB39886,
    0xBFFFD0,
    0x163A59,
    0x8C235B,
    0x8C5E00,
    0x00733D,
    0x000C59,
    0xFFBFD9,
    0x4C3300,
    0x36D98D,
    0x3D3DF2,
    0x590018,
    0xF2C200,
    0x264D40,
    0xC8BFFF,
    0xF23D6D,
    0xD9C36C,
    0x2DB3AA,
    0xB380FF,
    0xFF0022,
    0x333226,
    0x005C73,
    0x7C29A6,
]
WH_REGEX = r"discord(app)?\.com\/api\/webhooks\/(?P<id>\d+)\/(?P<token>.+)"

attachedPictures = []
attachedPictureType = "empty"
attachedVideo = "empty"

def worth_posting_location(location, coordinates, retweeted, include_retweet):
    location = [location[i : i + 4] for i in range(0, len(location), 4)]

    for box in location:
        for coordinate in coordinates:
            if box[0] < coordinate[0] < box[2] and box[1] < coordinate[1] < box[3]:
                if not include_retweet and retweeted:
                    return False
                return True
    return False


def worth_posting_track(track, hashtags, text, retweeted, include_retweet):
    for t in track:
        if t.startswith("#"):
            if t[1:] in map(lambda x: x["text"], hashtags):
                if not include_retweet and retweeted:
                    return False
                return True
        elif t in text:
            if not include_retweet and retweeted:
                return False
            return True
    return False


def worth_posting_follow(
    tweeter_id,
    twitter_ids,
    in_reply_to_twitter_id,
    retweeted,
    include_reply_to_user,
    include_user_reply,
    include_retweet,
):
    if tweeter_id not in twitter_ids:
        worth_posting = False
        if include_reply_to_user:
            if in_reply_to_twitter_id in twitter_ids:
                worth_posting = True
    else:
        worth_posting = True
        if not include_user_reply and in_reply_to_twitter_id is not None:
            worth_posting = False

    if not include_retweet:
        if retweeted:
            worth_posting = False
    return worth_posting


def keyword_set_present(keyword_sets, text):
    for keyword_set in keyword_sets:
        keyword_present = [keyword.lower() in text.lower() for keyword in keyword_set]
        keyword_set_present = all(keyword_present)
        if keyword_set_present:
            return True
    return False


def blackword_set_present(blackword_sets, text):
    if blackword_sets == [[""]]:
        return False
    for blackword_set in blackword_sets:
        blackword_present = [blackword.lower() in text.lower() for blackword in blackword_set]
        blackword_set_present = all(blackword_present)
        if blackword_set_present:
            return True
    return False


class Processor:
    def __init__(self, status_tweet, discord_config):
        self.status_tweet = status_tweet
        self.discord_config = discord_config
        self.text = ""
        self.url = ""
        self.user = ""
        self.embed = None
        self.initialize()

    def worth_posting_location(self):
        if (
            self.status_tweet.get("coordinates", None) is not None
            and self.status_tweet["coordinates"].get("coordinates", None) is not None
        ):
            coordinates = [self.status_tweet["coordinates"]["coordinates"]]
        else:
            coordinates = []

        if (
            self.status_tweet.get("place", None) is not None
            and self.status_tweet["place"].get("bounding_box", None) is not None
            and self.status_tweet["place"]["bounding_box"].get("coordinates", None) is not None
        ):
            tmp = self.status_tweet["place"]["bounding_box"]["coordinates"]
        else:
            tmp = []

        for (
            tmp_
        ) in tmp:  # for some reason Twitter API places the coordinates into a triple array.......
            for c in tmp_:
                coordinates.append(c)

        return worth_posting_location(
            location=self.discord_config.get("location", []),
            coordinates=coordinates,
            retweeted=self.status_tweet["retweeted"] or "retweeted_status" in self.status_tweet,
            include_retweet=self.discord_config.get("IncludeRetweet", True),
        )

    def worth_posting_track(self):
        if "extended_tweet" in self.status_tweet:
            hashtags = sorted(
                self.status_tweet["extended_tweet"]["entities"]["hashtags"],
                key=lambda k: k["text"],
                reverse=True,
            )
        else:
            hashtags = sorted(
                self.status_tweet["entities"]["hashtags"], key=lambda k: k["text"], reverse=True
            )

        return worth_posting_track(
            track=self.discord_config.get("track", []),
            hashtags=hashtags,
            text=self.text,
            retweeted=self.status_tweet["retweeted"] or "retweeted_status" in self.status_tweet,
            include_retweet=self.discord_config.get("IncludeRetweet", True),
        )

    def worth_posting_follow(self):
        return worth_posting_follow(
            tweeter_id=self.status_tweet["user"]["id_str"],
            twitter_ids=self.discord_config.get("twitter_ids", []),
            in_reply_to_twitter_id=self.status_tweet["in_reply_to_user_id_str"],
            retweeted=self.status_tweet["retweeted"] or "retweeted_status" in self.status_tweet,
            include_reply_to_user=self.discord_config.get("IncludeReplyToUser", True),
            include_user_reply=self.discord_config.get("IncludeUserReply", True),
            include_retweet=self.discord_config.get("IncludeRetweet", True),
        )

    def initialize(self):
        if "retweeted_status" in self.status_tweet:
            if "extended_tweet" in self.status_tweet["retweeted_status"]:
                self.text = self.status_tweet["retweeted_status"]["extended_tweet"]["full_text"]
            elif "full_text" in self.status_tweet["retweeted_status"]:
                self.text = self.status_tweet["retweeted_status"]["full_text"]
            else:
                self.text = self.status_tweet["retweeted_status"]["text"]
        elif "extended_tweet" in self.status_tweet:
            self.text = self.status_tweet["extended_tweet"]["full_text"]
        elif "full_text" in self.status_tweet:
            self.text = self.status_tweet["full_text"]
        else:
            self.text = self.status_tweet["text"]

        for url in self.status_tweet["entities"].get("urls", []):
            if url["expanded_url"] is None:
                continue
            self.text = self.text.replace(
                url["url"], "[%s](%s)" % (url["display_url"], url["expanded_url"])
            )

        for userMention in self.status_tweet["entities"].get("user_mentions", []):
            self.text = self.text.replace(
                "@%s" % userMention["screen_name"],
                "[@%s](https://twitter.com/%s)"
                % (userMention["screen_name"], userMention["screen_name"]),
            )

        if "extended_tweet" in self.status_tweet:
            for hashtag in sorted(
                self.status_tweet["extended_tweet"]["entities"].get("hashtags", []),
                key=lambda k: k["text"],
                reverse=True,
            ):
                self.text = self.text.replace(
                    "#%s" % hashtag["text"],
                    "[#%s](https://twitter.com/hashtag/%s)" % (hashtag["text"], hashtag["text"]),
                )

        for hashtag in sorted(
            self.status_tweet["entities"].get("hashtags", []),
            key=lambda k: k["text"],
            reverse=True,
        ):
            self.text = self.text.replace(
                "#%s" % hashtag["text"],
                "[#%s](https://twitter.com/hashtag/%s)" % (hashtag["text"], hashtag["text"]),
            )
        self.text = unescape(self.text)
        self.url = "https://twitter.com/{}/status/{}".format(
            self.status_tweet["user"]["screen_name"], self.status_tweet["id_str"]
        )
        self.user = self.status_tweet["user"]["name"]

    def keyword_set_present(self):
        return keyword_set_present(self.discord_config.get("keyword_sets", [[""]]), self.text)

    def blackword_set_present(self):
        return blackword_set_present(self.discord_config.get("blackword_sets", [[""]]), self.text)

    def attach_field(self):
        if self.discord_config.get("IncludeQuote", True) and "quoted_status" in self.status_tweet:
            if self.status_tweet["quoted_status"].get("text"):
                text = self.status_tweet["quoted_status"]["text"]
                for url in self.status_tweet["quoted_status"]["entities"].get("urls", []):
                    if url["expanded_url"] is None:
                        continue
                    text = text.replace(
                        url["url"], "[%s](%s)" % (url["display_url"], url["expanded_url"])
                    )

                for userMention in self.status_tweet["quoted_status"]["entities"].get(
                    "user_mentions", []
                ):
                    text = text.replace(
                        "@%s" % userMention["screen_name"],
                        "[@%s](https://twitter.com/%s)"
                        % (userMention["screen_name"], userMention["screen_name"]),
                    )

                for hashtag in sorted(
                    self.status_tweet["quoted_status"]["entities"].get("hashtags", []),
                    key=lambda k: k["text"],
                    reverse=True,
                ):
                    text = text.replace(
                        "#%s" % hashtag["text"],
                        "[#%s](https://twitter.com/hashtag/%s)"
                        % (hashtag["text"], hashtag["text"]),
                    )

                text = unescape(text)
                self.embed.add_field(
                    name=self.status_tweet["quoted_status"]["user"]["screen_name"], value=text
                )

    def attach_media(self):
        
        global attachedPictureType
        global attachedPictures
        global attachedVideo
        
        if (
            self.discord_config.get("IncludeAttachment", True)
            and "retweeted_status" in self.status_tweet
        ):
            if (
                "extended_tweet" in self.status_tweet["retweeted_status"]
                and "media" in self.status_tweet["retweeted_status"]["extended_tweet"]["entities"]
            ):
                for media in self.status_tweet["retweeted_status"]["extended_tweet"]["entities"][
                    "media"
                ]:
                    if media["type"] == "photo":
                        attachedPictures.append(media["media_url_https"]),
                        attachedPictureType = "photo"
                    elif media["type"] == "video":
                        attachedPictures.append(media["media_url_https"]),
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "video"
                    elif media["type"] == "animated_gif":
                        attachedPictures.append(media["media_url_https"]),
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "gif"

            if "media" in self.status_tweet["retweeted_status"]["entities"]:
                for media in self.status_tweet["retweeted_status"]["entities"]["media"]:
                    if media["type"] == "photo":
                        attachedPictures.append(media["media_url_https"]),
                        attachedPictureType = "photo"
                    elif media["type"] == "video":
                        attachedPictures.append(media["media_url_https"]),
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "video"
                    elif media["type"] == "animated_gif":
                        attachedPictures.append(media["media_url_https"]),
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "gif"


            if (
                "extended_entities" in self.status_tweet["retweeted_status"]
                and "media" in self.status_tweet["retweeted_status"]["extended_entities"]
            ):
                for media in self.status_tweet["retweeted_status"]["extended_entities"]["media"]:
                    if media["type"] == "photo":
                        attachedPictures.append(media["media_url_https"]),
                        attachedPictureType = "photo"
                    elif media["type"] == "video":
                        attachedPictures.append(media["media_url_https"]),
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "video"
                    elif media["type"] == "animated_gif":
                        attachedPictures.append(media["media_url_https"]),
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "gif"
        else:
            if (
                "extended_tweet" in self.status_tweet
                and "media" in self.status_tweet["extended_tweet"]["entities"]
            ):
                for media in self.status_tweet["extended_tweet"]["entities"]["media"]:
                    if media["type"] == "photo":
                        attachedPictures.append(media["media_url_https"]),
                        attachedPictureType = "photo"
                    elif media["type"] == "video":
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "video"
                    elif media["type"] == "animated_gif":
                        attachedPictures.append(media["media_url_https"]),
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "gif"

            if "media" in self.status_tweet["entities"]:
                for media in self.status_tweet["entities"]["media"]:
                    if media["type"] == "photo":
                        attachedPictures.append(media["media_url_https"]),
                        attachedPictureType = "photo"
                    elif media["type"] == "video":
                        attachedPictures.append(media["media_url_https"]),
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "video"
                    elif media["type"] == "animated_gif":
                        attachedPictures.append(media["media_url_https"]),
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "gif"

            if (
                "extended_entities" in self.status_tweet
                and "media" in self.status_tweet["extended_entities"]
            ):
                for media in self.status_tweet["extended_entities"]["media"]:
                    if media["type"] == "photo":
                        attachedPictures.append(media["media_url_https"]),
                        attachedPictureType = "photo"
                    elif media["type"] == "video":
                        attachedPictures.append(media["media_url_https"]),
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "video"
                    elif media["type"] == "animated_gif":
                        attachedPictures.append(media["media_url_https"]),
                        attachedVideo = (media["expanded_url"])  
                        attachedPictureType = "gif"

    def create_embed(self):
        self.embed = Embed(
            colour=self.discord_config.get("Color", random.choice(COLORS)),
            url="https://twitter.com/{}/status/{}".format(
                self.status_tweet["user"]["screen_name"], self.status_tweet["id_str"]
            ),
            title=self.status_tweet["user"]["name"],
            description=self.text,
            timestamp=datetime.strptime(
                self.status_tweet["created_at"], "%a %b %d %H:%M:%S +0000 %Y"
            ),
        )

# I put this part in comments, cause I didn't want it in my feed, feel free to reactivate it, if you want it
#        self.embed.set_author(
#            name=self.status_tweet["user"]["screen_name"],
#            url="https://twitter.com/" + self.status_tweet["user"]["screen_name"],
#            icon_url=self.status_tweet["user"]["profile_image_url"],
#        )
        self.embed.set_footer(
            text="Tweet created on",
            icon_url="https://cdn1.iconfinder.com/data/icons/iconza-circle-social/64/697029-twitter-512.png",
        )

    def send_message(self, wh_url):
        match = re.search(WH_REGEX, wh_url)
        
        global attachedPictureType
        global attachedPictures
        global attachedVideo

        if match:
            webhook = Webhook.partial(
                int(match.group("id")), match.group("token"), adapter=RequestsWebhookAdapter()
            )
            try:
                if self.discord_config.get("CreateEmbed", True):
                    
                    if attachedPictureType == "photo" or attachedPictureType == "gif" or attachedPictureType == "video":
                        self.embed.set_image(url=attachedPictures[0]) # gifs/video are only allowed once per tweet, otherwise the first picture gets attached to the first embed
                    
                    webhook.send(
                        embed=self.embed,
                        content=self.discord_config.get("custom_message", "").format(
                            user=self.user, text=self.text, url=self.url
                        ),
                    )
                                
                    # check if there are more than 1 different pictures. Sometimes the first or only picture is attached twice, don't ask me why
                    if len(attachedPictures) > 1:
                        if len(attachedPictures) == 2 and attachedPictures[0] == attachedPictures[1]: # two pictures attached, but they're both the same
                            pass
                        else:
                            
                            if attachedPictures[0] == attachedPictures[1]: # first picture attached twice
                                start = 2
                            else: # first picture attached once
                                start = 1
                                    
                            for attachedPicture in attachedPictures[start:]:
                                time.sleep(1) # this needs a second of sleep time between every message, otherwise they could come in the wrong order, cause they're all sent at once
                                picEmbed = Embed(
                                    colour=self.discord_config.get("Color", random.choice(COLORS)),
                                    )
                                picEmbed.set_image(url=attachedPicture),
                                webhook.send(
                                    embed=picEmbed,
                                    )
                                        
                else:                    
                    if attachedPictureType == "photo" or attachedPictureType == "gif" or attachedPictureType == "video":
                        self.embed.set_image(url=attachedPictures[0]) # gifs/video are only allowed once per tweet, otherwise the first picture gets attached to the first embed
                    
                    webhook.send(
                        embed=self.embed,
                        content=self.discord_config.get("custom_message", "").format(
                            user=self.user, text=self.text, url=self.url
                        ),
                    )
                                
                    # check if there are more than 1 different pictures. Sometimes the first or only picture is attached twice, don't ask me why
                    if len(attachedPictures) > 1:
                        if len(attachedPictures) == 2 and attachedPictures[0] == attachedPictures[1]: # two pictures attached, but they're both the same
                            pass
                        else:
                            
                            if attachedPictures[0] == attachedPictures[1]: # first picture attached twice
                                start = 2
                            else: # first picture attached once
                                start = 1
                                    
                            for attachedPicture in attachedPictures[start:]:
                                time.sleep(1) # this needs a second of sleep time between every message, otherwise they could come in the wrong order, cause they're all sent at once
                                picEmbed = Embed(
                                    colour=self.discord_config.get("Color", random.choice(COLORS)),
                                    )
                                picEmbed.set_image(url=attachedPicture),
                                webhook.send(
                                    embed=picEmbed,
                                    )
                    
                attachedPictures.clear() # clear pictures                        
                attachedVideo = "empty" # reset attachedVideo to "empty"
                attachedPictureType = "empty" # reset attachedPictureType to "empty"
                    
            except discord.errors.NotFound as error:
                print(
                    f"---------Error---------\n"
                    f"discord.errors.NotFound\n"
                    f"The Webhook does not exist."
                    f"{error}\n"
                    f"-----------------------"
                )
            except discord.errors.Forbidden as error:
                print(
                    f"---------Error---------\n"
                    f"discord.errors.Forbidden\n"
                    f"The authorization token of your Webhook is incorrect."
                    f"{error}\n"
                    f"-----------------------"
                )
            except discord.errors.InvalidArgument as error:
                print(
                    f"---------Error---------\n"
                    f"discord.errors.InvalidArgument\n"
                    f"You modified the code. You can't mix embed and embeds."
                    f"{error}\n"
                    f"-----------------------"
                )
            except discord.errors.HTTPException as error:
                print(
                    f"---------Error---------\n"
                    f"discord.errors.HTTPException\n"
                    f"Your internet connection is whack."
                    f"{error}\n"
                    f"-----------------------"
                )
        else:
            print(
                f"---------Error---------\n"
                f"The following webhook URL is invalid:\n"
                f"{wh_url}\n"
                f"-----------------------"
            )


if __name__ == "__main__":
    p = Processor({}, {"keyword_sets": [[""]]})
    p.text = "Hello World!"
    print(p.keyword_set_present())
