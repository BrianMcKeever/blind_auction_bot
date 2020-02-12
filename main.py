import discord
import sqlite3
import re
import datetime
import traceback
import asyncio
import random
import secret

connection = sqlite3.connect("user.db")
cursor = connection.cursor()

bid_re = re.compile("^!\d+ \d+ [a-zA-z]+")
AUCTION_LENGTH = 90 #seconds
MINIMUM_BID = 10
MIN_BID_INCREMENT = 5
ranks = ["Alt", "Main"]

dkp_channel = None

class Bid:
    def __init__(self, character_name, max_bid, character_rank):
        self.character_name = character_name
        self.max_bid = max_bid
        self.character_rank = character_rank

    def sort_value(self):
        result = 10000
        if self.character_rank == "Alt":
            result -= 10000
        result += self.max_bid
        return result

class Auction:
    def __init__(self, item_name, auctioneer):
        self._item_name = item_name
        self._auctioneer = auctioneer
        self._bids = {}
        self.start()

    def get_starting_time(self):
        return self._auction_start

    def get_item_name(self):
        return self._item_name

    def finish(self):
        self._status = "finished"

    def cancel(self):
        self._status = "canceled"

    def pause(self):
        self._status = "paused"

    def resume(self):
        self._status = "started"
        self._auction_start = datetime.datetime.now()

    def start(self):
        self._status = "started"
        self._auction_start = datetime.datetime.now()

    def add_bid(self, bid):
        if self._status == "finished":
            return False
        self._bids[bid.character_name] = bid
        return True

    def cancel_bid(self, character_name):
        if character_name in self._bids.keys():
            del self._bids[character_name]
            return True
        return False

    def is_over(self):
        return self._status == "finished"

    def get_results(self):
        if self._status != "finished":
            raise "Listing not over"

        if len(self._bids.values()) == 0:
            return None

        bids = list(self._bids.values())
        random.shuffle(bids)
        sorted_bids = sorted(bids, reverse = True, key = lambda x: x.sort_value())
        highest_bid = None
        second_highest_bid = None

        if len(sorted_bids) == 0:
            return None

        count_ties = 0
        highest_bid = sorted_bids[0]
        for bid in sorted_bids[1:]:
            if bid.sort_value() == highest_bid.sort_value():
                count_ties += 1
            else:
                break

        if count_ties > 0:
            return ("tie", sorted_bids)
        return ("winner", sorted_bids)

    def update_bid_rank(self, character_name, rank):
        if self._status == "finished":
            return False
        self._bids[character_name].character_rank = rank
        return True

    def get_status(self):
        return self._status


class Slots:
    def __init__(self):
        self._slots = [None] * 100
        self._slot_counter = 0

    def append(self, auction):
        self._slots[self._slot_counter] = auction
        result = self._slot_counter
        if self._slot_counter <= 99:
            self._slot_counter += 1
        else:
            self._slot_counter = 0
        return result

    def get(self, n):
        if n < 0 or n > 99:
            return None
        return self._slots[n]


client = discord.Client()
slots = Slots()

def is_valid_rank(rank):
    return rank in ranks

async def get_dm_channel(user):
    if user.dm_channel is None:
        channel = await user.create_dm()
    else:
        channel = user.dm_channel
    return channel

async def authorized(name, character_name, channel):
    result = list(cursor.execute("select discord_name from user where name = ?", (character_name,)))
    if len(result) == 0:
        await channel.send("That character wasn't found."%(character_name, discord_name))
        return False
    discord_name = result[0][0]
    if discord_name != name:
        await channel.send('You are not authorized to control %s. That character is owned by discord name %s. If this is a mistake, please contact Ixrak.'%(character_name, discord_name))
        return False
    return True


async def auction_loop():
    while True:
        for i in range(0, 100):
            auction = slots.get(i)
            if auction == None:
                continue
            if auction.get_status() != "started":
                continue
            duration = datetime.datetime.now() - auction.get_starting_time()
            if duration.total_seconds() >= AUCTION_LENGTH:
                auction.finish()
                item_name = auction.get_item_name()
                text = 'The auction for "%s" is over.'%(item_name)
                results = auction.get_results()
                if results == None:
                    text = text + ' No one bid on "%s".'%(item_name)
                    await dkp_channel.send(text)
                    continue

                bids = results[1]
                if len(bids) == 1:
                    text = text + " %s is the only person that bid. They get the item for %s dkp."%(bids[0].character_name, MINIMUM_BID)
                    await dkp_channel.send(text)
                    continue

                if bids[0].character_rank == "Alt":
                    second_highest_bid = bids[1].max_bid
                    if second_highest_bid == bids[0].max_bid:
                        cost = second_highest_bid
                    else:
                        cost = second_highest_bid + MIN_BID_INCREMENT
                        if cost > bids[0].max_bid:
                            cost = bids[0].max_bid
                elif bids[1].character_rank == "Alt":
                    cost = MINIMUM_BID
                else:
                    second_highest_bid = bids[1].max_bid
                    if second_highest_bid == bids[0].max_bid:
                        cost = second_highest_bid
                    else:
                        cost = second_highest_bid + MIN_BID_INCREMENT
                        if cost > bids[0].max_bid:
                            cost = bids[0].max_bid

                text += " %s wins. They get the item for %s dkp."%(bids[0].character_name, cost)

                for bid in bids:
                    text = text + "\n%s bid %s and is a %s."%(bid.character_name, bid.max_bid, bid.character_rank)
                await dkp_channel.send(text)

        await asyncio.sleep(1)


@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client), flush=True)
    for channel in client.guilds[0].channels:
        if channel.name == "dkp":
            global dkp_channel
            dkp_channel = channel
            break
    else:
        print("The #dkp channel doesn't seem to exist. Maybe, I don't have access?", flush = True)


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if hasattr(message.channel, "name") and message.channel.name != "dkp":
        return

    if message.content.startswith('!help'):
        channel = await get_dm_channel(message.author)
        if message.channel == dkp_channel:
            await message.delete()
        if message.content.strip() == "!help":
            await channel.send(
                """
Remember, all commands have to be typed exactly maintaining the spacing and case-sensitivity.

How bidding works is that everyone who is interested in an item bids their maximum bid.  After a %s seconds, the auction will expire and the item will be awarded to the top bidder at the price of the second highest bidder's maximum bid +5 DKP. If no one else bids, you'll get it for 10 DKP.

If you've never raided with us before, you start with 50 DKP.

To bid on an item, private message me "!the_slot_number your_maximum_bid the_name_of_the_character_you're_bidding_for".
For example, if the listing was "Listing motor oil in slot 13" and my character GasGuzzler would pay up to 300 DKP for that, I would private message me "!13 300 GasGuzzler".

Type "!help auctioning" if you want help auctioning items.
Type "!why" if you want to know why we are trying this.
            """%(AUCTION_LENGTH))

        elif message.content.strip() == "!help auctioning":
            await channel.send("""
To list an item, type "!list item_name".
To cancel an auction, type !cancel slot_number".
To pause an auction, type !pause slot_number".
To resume an auction, type !resume slot_number".
            """)
        else:
            await channel.send("Unknown help topic")

    elif message.content.startswith('!why'):
        channel = await get_dm_channel(message.author)
        if message.channel == dkp_channel:
            await message.delete()
        await channel.send(
                """
Speed: we should be able to bid on and resolve multiple items quicker this way.
Attention: this method should require less attention. You'll no longer have to pay attention to auctions in progress to bid. Bid once and you're done.
Value: If you bid in large increments to speed up the bidding process, this method should save you DKP by giving you the second_highest_bidder's max price +5.
Regularity: All auctions will end after %s seconds, so there isn't some arbitrary cut off time that changes depending on the mood of the auctioneer.
Concurrency: This method allows alts and mains to bid at the same time without confusion (mains still get priority).  """%(AUCTION_LENGTH))

    elif message.content.startswith('!pause '):
        try:
            tokenized = message.content.split(" ")
            if len(tokenized) != 2:
                await message.channel.send("The format is !pause slot_number")
                return
            slot_number = int(tokenized[1])
            auction = slots.get(slot_number)
            if auction is None:
                await message.channel.send("That slot is not being used.")
                return
            auction.pause()
            await message.channel.send("The \"%s\" has been paused. Type \"!resume %s\" when you are ready to restart the auction."%(auction.get_item_name(), slot_number))
            if message.channel != dkp_channel:
                await dkp_channel.send("The \"%s\" in slot %s has been paused by %s"%(auction.get_item_name(), slot_number, message.author.name))
        except sqlite3.OperationalError:
            print("Database locked!", flush = True)
            await channel.send('Bot error: the database is locked.')
        except Exception as e:
            print(e, flush = True)
            print(message.content, flush = True)
            print(traceback.format_exc(), flush = True)
            await message.channel.send("The format is !pause slot_number")

    elif message.content.startswith('!cancel '):
        try:
            tokenized = message.content.split(" ")
            if len(tokenized) != 2:
                await message.channel.send("The format is !cancel slot_number")
                return
            slot_number = int(tokenized[1])
            auction = slots.get(slot_number)
            if auction is None:
                await message.channel.send("That slot is not being used.")
                return
            auction.cancel()
            await message.channel.send("The \"%s\" has been canceled."%(auction.get_item_name()))
            if message.channel != dkp_channel:
                await dkp_channel.send("The \"%s\" in slot %s has been canceled by %s"%(auction.get_item_name(), slot_number, message.author.name))
        except sqlite3.OperationalError:
            print("Database locked!", flush = True)
            await channel.send('Bot error: the database is locked.')
        except Exception as e:
            print(e, flush = True)
            print(message.content, flush = True)
            print(traceback.format_exc(), flush = True)
            await message.channel.send("The format is !pause slot_number")

    elif message.content.startswith('!resume '):
        try:
            tokenized = message.content.split(" ")
            if len(tokenized) != 2:
                await message.channel.send("The format is !resume slot_number")
                return
            slot_number = int(tokenized[1])
            auction = slots.get(slot_number)
            if auction is None:
                await message.channel.send("That slot is not being used.")
                return
            auction.resume()
            await message.channel.send("The \"%s\" has been resumed."%(auction.get_item_name()))
            if message.channel != dkp_channel:
                await dkp_channel.send("The \"%s\" in slot %s has been resumed by %s"%(auction.get_item_name(), slot_number, message.author.name))
        except sqlite3.OperationalError:
            print("Database locked!", flush = True)
            await channel.send('Bot error: the database is locked.')
        except Exception as e:
            print(e, flush = True)
            print(message.content, flush = True)
            print(traceback.format_exc(), flush = True)
            await message.channel.send("The format is !resume slot_number")

    elif message.content.startswith('!list'):
        try:
            item_name = message.content.split(" ", 1)[1].strip()
            auction = Auction(item_name, message.author.name)
            slot_number = slots.append(auction)
            if message.channel != dkp_channel:
                await message.channel.send('Listing "%s" for auction in slot %s.  Bidding will end in %s seconds. Private message me "!%s your_max_bid your_character_name" to bid or "!help" for more instructions.'%(item_name, slot_number, AUCTION_LENGTH, slot_number))
                await dkp_channel.send('%s has listed "%s" for auction in slot %s. Bidding will end in %s seconds. Private message me !help for instructions on how to bid.'%(message.author.name, item_name, slot_number, AUCTION_LENGTH))
            else:
                await message.channel.send('Listing "%s" for auction in slot %s.  Bidding will end in %s seconds. Private message me "!%s your_max_bid your_character_name" to bid or "!help" for more instructions.'%(item_name, slot_number, AUCTION_LENGTH, slot_number))
            return
        except sqlite3.OperationalError:
            print("Database locked!", flush = True)
            await channel.send('Bot error: the database is locked.')
        except Exception as e:
            print(e, flush = True)
            print(message.content, flush = True)
            print(traceback.format_exc(), flush = True)
            await dkp_channel.send('The format to list an item is "!list item_name"')

    elif message.content.startswith('!new_character '):
        channel = await get_dm_channel(message.author)
        if message.channel == dkp_channel:
            await message.delete()
        try:
            tokenized = message.content.split(" ")
            name = tokenized[1].capitalize()
            rank = tokenized[2].capitalize()
            discord_name = message.author.name

            if not is_valid_rank(rank):
                await channel.send('Your new status is invalid. It must be one of these %s.'%(", ".join(ranks)))
                return

            result = list(cursor.execute("select * from user where name = ?", (name,)))
            if len(result) != 0:
                await channel.send('That character already exists in the database.')
                return

            cursor.execute("insert into user values (?, ?, ?)", (name, rank, discord_name))
            connection.commit()
            await channel.send('Your character, %s, has been added to the database as an %s.'%(name, rank))
        except sqlite3.OperationalError:
            print("Database locked!", flush = True)
            await channel.send('Bot error: the database is locked.')
        except Exception as e:
            print(e, flush = True)
            print(message.content, flush = True)
            print(traceback.format_exc(), flush = True)
            await channel.send('The format for the command is "!new_character character_name your_characters_rank')

    elif message.content.startswith('!status '):
        discord_name = message.author.name
        channel = await get_dm_channel(message.author)
        if message.channel == dkp_channel:
            await message.delete()

        try:
            tokenized = message.content.split(" ", 3)
            name = tokenized[1].capitalize()
            rank = tokenized[2].capitalize()

            if not await authorized(discord_name, name, channel):
                return

            if not is_valid_rank(rank):
                await channel.send('Your new status is invalid. It must be one of these %s.'%(", ".join(ranks)))
                return

            result = list(cursor.execute("select * from user where name = ?", (name,)))
            if len(result) == 0:
                await channel.send('That character was not found in the database.')
                return

            cursor.execute("update user set rank = ? where name = ?", (rank, name))
            connection.commit()
            await channel.send('Your character, %s, has had their status updated to %s.'%(name, rank))
            return
        except sqlite3.OperationalError:
            print("Database locked!", flush = True)
            await channel.send('Bot error: the database is locked.')
        except Exception as e:
            print(e, flush = True)
            print(message.content, flush = True)
            print(traceback.format_exc(), flush = True)
            await channel.send('The format for the command is "!status character_name your_characters_status')

    elif message.content.startswith('!cancel_bid '):
        channel = await get_dm_channel(message.author)
        if message.channel == dkp_channel:
            await message.delete()

        try:
            tokenized = message.content.split(" ")
            if len(tokenized) != 3:
                await channel.send("The format is !cancel_bid slot_number character_name")
                return
            slot_number = int(tokenized[1])
            character_name = tokenized[2].strip().capitalize()

            if not await authorized(message.author.name, character_name, channel):
                return

            auction = slots.get(slot_number)
            if auction is None:
                await channel.send("That slot is not being used.")
                return
            result = auction.cancel_bid(character_name)
            if result:
                await channel.send("Your bid on the \"%s\" has been canceled."%(auction.get_item_name()))
            else:
                await channel.send("You did not have a bid to cancel.")
        except sqlite3.OperationalError:
            print("Database locked!", flush = True)
            await channel.send('Bot error: the database is locked.')
        except Exception as e:
            print(e, flush = True)
            print(message.content, flush = True)
            print(traceback.format_exc(), flush = True)
            await channel.send("The format is !cancel_bid slot_number character_name")

    elif bid_re.match(message.content):
        channel = await get_dm_channel(message.author)
        if message.channel == dkp_channel:
            await message.delete()
        try:
            tokenized = message.content.split(" ")
            slot_number = int(tokenized[0][1:])
            max_bid = int(tokenized[1])
            character_name = tokenized[2].strip().capitalize()
            result = list(cursor.execute("select * from user where name = ?", (character_name,)))
            auction = slots.get(slot_number)

            if len(result) == 0:
                await channel.send("That character name was not found.  If it is a new character, please type \"!new_character character_name your_character's_status\" and bid again.")
                return
            elif auction == None:
                await channel.send("That listing does not exist.")
                return
            elif auction.get_status() == "finished":
                await channel.send("That auction has already finished. Sorry.")
                return
            elif auction.get_status() == "canceled":
                await channel.send("That auction was canceled. Sorry.")
                return
            elif len(result) == 1:
                result = result[0]
                character_rank = result[1]
                discord_name = result[2]
                if message.author.name == discord_name or discord_name is None:
                    if discord_name == None:
                        cursor.execute("update user set discord_name = ? where name = ?", (message.author.name, character_name))
                        connection.commit()
                    bid = Bid(character_name, max_bid, character_rank)
                    success = auction.add_bid(bid)
                    if success:
                        await channel.send('''You have bid %s as %s who is a %s for the "%s".
If your main status is wrong, change this ASAP by typing, "!status character_name new_status".
If you'd like to cancel your bid, type "!cancel_bid %s %s"'''%(max_bid, character_name, character_rank, auction.get_item_name(), slot_number, character_name))
                    else:
                        await channel.send("You were too late to bid. Sorry.")
                    return
                else:
                    await channel.send('You are not authorized to bid for %s. That character is owned by discord name %s. If this is a mistake, please contact Ixrak.'%(character_name, discord_name))
            else:
                f = open("error_log.txt", a)
                f.write("Two results %s from %s\n"%(message.content, message.author.name))
                f.close()

                await channel.send('Somehow, your character name pulled up two results. Message Ixrak for help resolving this.')

        except sqlite3.OperationalError:
            print("Database locked!", flush = True)
            await channel.send('Bot error: the database is locked.')
        except Exception as e:
            print(e, flush = True)
            print(message.content, flush = True)
            print(traceback.format_exc(), flush = True)
            await channel.send("The format is '!slot_number max_bid your_character_name'")

client.loop.create_task(auction_loop())
client.run(secret.token)
connection.close()
