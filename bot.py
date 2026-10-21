import os
import discord
from discord.ext import tasks, commands
import sqlite3
import datetime
from dateutil import parser
import pickle
import re

db_path = '/data/schedule.db'

with sqlite3.connect(db_path) as db_conn:

    db_cursor = db_conn.cursor()

    create_schedule = """CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY,
        type TEXT NOT NULL,
        datetime INTEGER,
        role INTEGER,
        source_channel INTEGER,
        source_message INTEGER,
        dest INTEGER
    );"""

    insert_message = "INSERT INTO schedule(type, datetime, source_channel, source_message, dest) VALUES('message',?,?,?,?)"
    insert_role = "INSERT INTO schedule(type, datetime, source_channel, source_message, dest) VALUES('role',?,?,?,?)"
    cancel_event = "DELETE FROM schedule WHERE id = ?"
    select_event = "SELECT * FROM schedule WHERE id = ?"
    select_message_now = "SELECT id, source_channel, source_message, dest FROM schedule WHERE datetime <= datetime('now') AND type = 'message'"
    select_role_now = "SELECT id, source_channel, source_message, dest FROM schedule WHERE datetime <= datetime('now') AND type = 'role'"
    complete_event = cancel_event
    select_all = "SELECT * FROM schedule"

    db_cursor.execute(create_schedule)
    db_conn.commit()

    print("Loaded schedule: {")
    for row in db_conn.execute(select_all).fetchall():
        print(row)
    print("}")

    TOKEN = os.environ['BOT_TOKEN']

    intents = discord.Intents.all()

    bot = commands.Bot(command_prefix='$', intents=intents)

    @bot.event
    async def on_ready():
        print(f'We have logged in as {bot.user}')
        read_schedule.start()


    class CancelButton(discord.ui.View):
        def __init__(self, rowid):
            super().__init__(timeout=None)
            self.rowid = rowid
        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
        async def continue_button(self,interaction:discord.Interaction,button:discord.ui.Button):
            cabal = discord.utils.get(interaction.guild.roles, name="Cabal")
            if interaction.user.get_role(cabal.id):
                db_cursor.execute(cancel_event, (self.rowid,))
                db_conn.commit()
                await interaction.message.delete()

    async def send_message(source_channel_id, message_id, dest_channel_id):
        try:
            source_channel = bot.get_channel(source_channel_id)
            dest_channel = bot.get_channel(dest_channel_id)
            message = await source_channel.fetch_message(message_id)
            files = [await x.to_file() for x in message.attachments]
            await dest_channel.send(message.content, files=files)
            await source_channel.send(f"Sent message in <#{dest_channel.id}>")
        except:
            print("Failed to send message")
            return

    async def assign_role(source_channel_id, message_id, role_id):
        try:
            source_channel = bot.get_channel(source_channel_id)
            guild = source_channel.guild
            role = guild.get_role(role_id)
            message = await source_channel.fetch_message(message_id)
            for member in message.content.split():
                try:
                    member = guild.get_member(int(re.match(r"<@([0-9]+)>", member).group(1)))
                    await member.add_roles(role)
                    await source_channel.send(f"Added <@{member.id}> to <@&{role.id}>")
                except:
                    print("Error adding member to role")
                    await source_channel.send(f"Error adding '{str(member)}' to <@&{role.id}>")
        except:
            return


    @bot.command(name='schedule-cancel')
    @commands.has_role("Cabal")
    async def schedule_cancel(ctx, rowid):
        """ Cancel a scheduled role or message with its ID """
        if 0 == len(db_cursor.execute(select_event, (rowid,)).fetchall()):
            await ctx.send("Could not find event")
            return
        try:
            db_cursor.execute(delete_event, (rowid,))
            db_conn.commit()
            await ctx.send("Successfully deleted scheduled event")
        except:
            print("Failed to delete scheduled event")
            await ctx.send("Failed to delete scheduled event")

    @bot.command(name='schedule-message')
    @commands.has_role("Cabal")
    async def schedule_message(ctx, sched_channel: discord.TextChannel, *, sched_datetime):
        """ Schedule a message to be posted in some channel at some time """
        try:
            if sched_datetime != "now":
                sched_datetime = parser.parse(sched_datetime)
                if sched_datetime < datetime.datetime.now():
                    await ctx.send("Error: Date/time is in the past")
                    return

        except:
            await ctx.send("Error: Cannot parse date/time")
            return
        conf = await ctx.send(f"Scheduling a message in <#{sched_channel.id}> for {str(sched_datetime)}\nWhat would you like the message to say?")
        res = await bot.wait_for(
            "message",
            check=lambda x: x.channel.id == ctx.channel.id
            and ctx.message.author.id == x.author.id,
            timeout=180,
        )
        if res:
            db_cursor.execute(insert_message, (str(sched_datetime), ctx.channel.id, res.id, sched_channel.id))
            sched_rowid = db_cursor.lastrowid
            await ctx.send(f"Scheduled message in <#{sched_channel.id}> for {str(sched_datetime)}\n-# [Event ID {sched_rowid}]", view=CancelButton(sched_rowid))
            db_conn.commit()

    @bot.command(name='schedule-role')
    @commands.has_role("Cabal")
    async def schedule_message(ctx, sched_role: discord.Role, *, sched_datetime):
        """ Schedule a list of members to be given a role at some time """
        try:
            if sched_datetime != "now":
                sched_datetime = parser.parse(sched_datetime)
                if sched_datetime < datetime.datetime.now():
                    await ctx.send("Error: Date/time is in the past")
                    return
        except:
            await ctx.send("Error: Cannot parse date/time")
            return
        conf = await ctx.send(f"Scheduling assignment of <@&{sched_role.id}> for {str(sched_datetime)}\nWhich users should be added to the role? (space seperated list)")
        res = await bot.wait_for(
            "message",
            check=lambda x: x.channel.id == ctx.channel.id
            and ctx.message.author.id == x.author.id,
            timeout=180,
        )
        if res:
            db_cursor.execute(insert_role, (str(sched_datetime), ctx.channel.id, res.id, sched_role.id))
            sched_rowid = db_cursor.lastrowid
            await ctx.send(f"Scheduled assignment of <@&{sched_role.id}> for {str(sched_datetime)}\n-# [Event ID {sched_rowid}]", view=CancelButton(sched_rowid))
            db_conn.commit()

    @tasks.loop(seconds=10)
    async def read_schedule():
        for (rowid, source_channel, source_message, dest_channel) in db_conn.execute(select_message_now).fetchall():
            await send_message(source_channel, source_message, dest_channel)
            db_conn.execute(complete_event, (rowid,))
            db_conn.commit()
        for (rowid, source_channel, source_message, role) in db_conn.execute(select_role_now).fetchall():
            await assign_role(source_channel, source_message, role)
            db_conn.execute(complete_event, (rowid,))
            db_conn.commit()

    bot.run(TOKEN)
