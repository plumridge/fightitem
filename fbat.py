import json
import os
import random
import sys

from PIL import Image
import twitter
import boto3

GAMES = ["ff1", "ff4", "ff6"]

def clean_command(cmd):
    cmd = cmd.replace("_", " ")
    cmd = cmd.replace(".", "")
    cmd = cmd.replace("-", " ")
    cmd = cmd.replace(",", "")
    return cmd

def get_dictionaries(s3=None):
    menu, verbs = None, None
    
    if s3 != None:
        s3_obj = s3.get_object(Bucket="fbat", Key="data/verb.dict")
        body = s3_obj["Body"]
        verbs = body.read().decode("utf-8").split("\n")

        s3_obj = s3.get_object(Bucket="fbat", Key="data/menu.dict")
        body = s3_obj["Body"]
        menu = body.read().decode("utf-8").split("\n")
    else:
        f = open("data/menu.dict")
        menu = f.readlines()

        f = open("data/verb.dict")
        verbs = f.readlines()

    #strip trailing newline
    menu.pop(-1)
    verbs.pop(-1)

    return menu, verbs

def get_offset(game, s3=None):
    offset = None
    if s3 != None:
        s3_obj = s3.get_object(Bucket="fbat", Key="data/" + game + "/offset.json")
        of = s3_obj["Body"]
        offset = json.load(of)
    else:
        f = open("data/" + game + "/offset.json")
        offset = json.load(f)
        f.close()
    return offset

def create_menu(menu_list, verb_list, offset):
    random.seed()
    commands = []
    blanks = 0
    menulength = offset["listlength"] * offset["columns"]
    #some games will have 'Item' already drawn to the end of the list, some don't
    #including this already drawn 'Item' in the list length avoids other problems
    if offset["add-item"]:
        menulength = menulength - 1
    while len(commands) < menulength - blanks:
        cmd_src = random.randint(0, 100)
        if cmd_src < 82:
            cmd = random.choice(verb_list)
        elif cmd_src < 93:
            if len(commands) == 0:
                cmd = "fight"
            else:
                cmd = menu_list.pop(random.randrange(len(menu_list)))
        elif offset["blanks"] and len(commands) > 0:
            #some games allow blank commands in the middle of the list, others compress the list
            if offset["blanks-at-end"]:
                blanks = blanks + 1
                continue
            else:
                cmd = ""
        else:
            continue

        cmd = cmd.replace("\n", "")
        if len(cmd) > offset["commandlength"]:
            continue
        cmd = clean_command(cmd)
        commands.append(cmd)
    if offset["add-item"]:
        commands.append("item")

    for i, cmd in enumerate(commands):
        if cmd == "":
            continue

        if offset["uppercase"]:
            commands[i] = cmd.upper()
        else:
            #uppercase first letter only
            commands[i] = cmd[0].upper() + cmd[1:]

    return commands

def draw(game, menu, offset, s3=None):
    img_path, img, font = None, None, None

    if s3 != None:
        img_paths = s3.list_objects(Bucket="fbat", Prefix="data/" + game + "/img")
        img_path = random.choice(img_paths["Contents"])["Key"]
        img_obj = s3.get_object(Bucket="fbat", Key=img_path)

        font_obj = s3.get_object(Bucket="fbat", Key="data/" + game + "/font.png")

        img = Image.open(img_obj["Body"])
        font = Image.open(font_obj["Body"])
    else:
        data_root = "data/" + game + "/"
        img_paths = os.listdir(data_root + "img")
        img_path = data_root + "img/" + random.choice(img_paths)
        img = Image.open(img_path)
        font = Image.open(data_root + "font.png")

    height = offset["height"]
    origins = offset["origin"]

    origin_idx = -1
    for i,cmd in enumerate(menu):
        if i % offset["listlength"] == 0: 
            origin_idx = origin_idx + 1
            origin_x = origins[origin_idx]["x"]            
            origin_y = origins[origin_idx]["y"]
            x_pos = origin_x
            y_pos = origin_y
        for c in cmd:
            char = offset[str(ord(c))]
            crop = font.crop((char["x"], 0, char["x"] + char["w"], height))
            img.paste(crop, (x_pos, y_pos), crop)
            x_pos = x_pos + char["w"]
        x_pos = origin_x
        y_pos = y_pos + height + offset["linespace"]

    img_width, img_height = img.size
    img = img.resize((img_width*4, img_height*4), Image.NEAREST)
    if s3 != None:
        img.save('/tmp/out.png')
    else:
        img.save("/mnt/c/hold/test.png")

#Assumes image stored in '/tmp/out.png'
def tweet():
    outfile = open("/tmp/out.png", "rb")
    api = twitter.Api(
            consumer_key=os.environ.get("TWITTER_CONSUMER_KEY"),
            consumer_secret=os.environ.get("TWITTER_CONSUMER_SECRET"),
            access_token_key=os.environ.get("TWITTER_ACCESS_TOKEN_KEY"),
            access_token_secret=os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")
    )
    api.PostUpdate(status='', media=outfile)
    outfile.close()

#Fires on local execution
def main():
    #Check for argument 1 with valid game name
    if len(sys.argv) > 1 and sys.argv[1] in GAMES:
        game = sys.argv[1]
    else:
        game = random.choice(GAMES)

    menu_list, verb_list = get_dictionaries()
    offset = get_offset(game)
    commands = create_menu(menu_list, verb_list, offset)

    print("~~~~" + game + "~~~~")
    for cmd in commands:
        if cmd == "": print("-----")
        else: print(cmd)
    draw(game, commands, offset)

#Fires on lambda execution
def lambda_handler(event, context):
    game = random.choice(GAMES)
    s3 = boto3.client("s3")

    menu_list, verb_list = get_dictionaries(s3)
    offset = get_offset(game, s3)
    commands = create_menu(menu_list, verb_list, offset)
    draw(game, commands, offset, s3)
    tweet()

    return None

#Calls 'main' if run normally from a command line (as opposed to lambda)
if __name__ == "__main__":
    main()