from discord.ext import commands
from lib.mysql import mysql
from typing import Optional
import discord
import lib.embedder
import os

class FriendCode(commands.Cog):
    def __init__(self, client):
        self.client = client

    def is_guild_owner():
        def predicate(ctx):
            return ctx.guild is not None and ctx.guild.owner_id == ctx.author.id
        return commands.check(predicate)

    @commands.group(
        name = "friendcode",
        aliases = ["fc"],
        brief = "Friend Code Sharing System",
        description = "Cherubi Bot - Friend Code Sharing System",
        usage = "[tagged user] [filter] | <add | list | remove>",
        help = "You can run the command without a tagged user to bring up your info, tag a user to bring up theirs, or run one of the subcommands that are below.",
        invoke_without_command = True
    )
    async def friendcode_group(self, ctx, target: Optional[discord.Member], filter = None):
        # If no target is given, use the user who wrote the command
        target = target or ctx.author

        db = mysql()
        query = """
            SELECT
                up.home_guild AS home_guild,
                up.fc_visibility AS visibility,
                fc.identifier AS identifier,
                fc.code AS code
            FROM friend_codes fc
            LEFT JOIN user_preferences up ON up.user_id = fc.user_id
            WHERE fc.user_id = %s
            AND fc.identifier LIKE %s
            ORDER BY fc.identifier ASC;
        """
        results = db.query(query, [target.id, f"%{filter if filter else ''}%"])
        db.close()

        # Check if the target has any friend codes on file. If not, send a
        # warning embed and return.
        if not results:
            if filter:
                await ctx.send(embed = lib.embedder.make_embed(
                    type = "warning",
                    title = f"{target.display_name}'s Friend Codes",
                    content = f"No friend codes were found for `{target.display_name}` with `{filter}` in it"
                ))
                return
            else:
                await ctx.send(embed = lib.embedder.make_embed(
                    type = "warning",
                    title = f"{target.display_name}'s Friend Codes",
                    content = f"Sadly `{target.display_name}` doesn't have any friend codes stored."
                ))
                return

        # Check if the user's visibility is hidden. If so, give an error and return.
        if target.id != ctx.author.id and results[0]['visibility'] == "hidden":
            await ctx.send(embed = lib.embedder.make_embed(
                type = "error",
                title = f"{target.display_name}'s Friend Codes",
                content = f"`{target.display_name}` has their friend code visibility set to hidden. Only they can send them."
            ))
            return

        # Check if they have a home server set. If not, give an error and return.
        if target.id != ctx.author.id and not results[0]['home_guild']:
            await ctx.send(embed = lib.embedder.make_embed(
                type = "error",
                title = f"{target.display_name}'s Friend Codes",
                content = f"`{target.display_name}` doesn't have a home server set.",
                footer = f"They need to run !sethome"
            ))
            return

        # Check if the target is the original author,
        # if not then check if their visibility is private,
        # if it is then check if this is their home guild.
        # If it isn't, send an error embed and return.
        if (target.id != ctx.author.id
            and (not results[0]['visibility'] or results[0]['visibility'] == "private")
            and results[0]['home_guild'] != ctx.guild.id):
            await ctx.send(embed = lib.embedder.make_embed(
                type = "error",
                title = f"{target.display_name}'s Friend Codes",
                content = f"This is not `{target.display_name}`'s home server and their visibility is set to private."
            ))
            return

        # For every result returned, send an embed with the friend code and
        for result in results:
            code = str(result['code']).zfill(12)
            await ctx.send(embed = lib.embedder.make_embed(
                type = "info",
                title = f"F.C. for {result['identifier']}",
                content = code,
                thumbnail = f"https://chart.googleapis.com/chart?chs=300x300&cht=qr&chl={code}",
                footer = f"Owned by {target.display_name}"
            ))

    @friendcode_group.command(
        name = "add",
        aliases = ["a"],
        brief = "Adds / edits a friend code on your list",
        description = "Cherubi Bot - Friend Code Sharing System",
        usage = "<trainer name> <friend code>",
        help = "This adds the given friend code to your list. If you run this again with the same trainer name, it'll change the friend code for it."
    )
    async def add_subcommand(self, ctx, input_identifier, code, code_part2 = "", code_part3 = ""):
        # This and the additional two code "parts" are for if the user
        # uses a separated version of the friend code.
        if code_part2 != "" or code_part3 != "":
            code = code + code_part2 + code_part3

        # Checks if the identifier if over 16 characters long. If so then send
        # an error embed and return.
        if len(input_identifier) > 16:
            await ctx.send(embed = lib.embedder.make_embed(
                type = "error",
                title = f"Error Adding Friend Code",
                content = "The trainer name / identifier that you gave is longer than the maximum character limit."
            ))
            return

        # Check that the friend code was numbers and that it was 12 digits long,
        # if it isn't then send an error embed and return
        if not code.isdigit() or len(code) != 12:
            await ctx.send(embed = lib.embedder.make_embed(
                type = "error",
                title = f"Error Adding Friend Code",
                content = "The given friend code isn't all numbers."
            ))
            await ctx.send_help(str(ctx.command))
            return

        if len(code) != 12:
            await ctx.send(embed = lib.embedder.make_embed(
                type = "error",
                title = f"Error Adding Friend Code",
                content = "The given friend code isn't 12 digits long."
            ))
            await ctx.send_help(str(ctx.command))
            return

        db = mysql()
        query = """
            INSERT INTO friend_codes (user_id, identifier, code)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE code = VALUES(code);
        """
        db.execute(query, [
            ctx.message.author.id,
            input_identifier,
            code
        ])
        db.close()

        await ctx.send(embed = lib.embedder.make_embed(
            type = "success",
            title = f"Added Friend Code",
            content = f"Added friend code `{code}` for `{input_identifier}`."
        ))

    @friendcode_group.command(
        name = "list",
        aliases = ["l"],
        brief = "Lists all of your friend codes in a single message",
        description = "Cherubi Bot - Friend Code Sharing System",
        help = "This lists all of your friend codes in a single message. This command is not mobile friendly."
    )
    async def list_subcommand(self, ctx):
        db = mysql()
        query = """
            SELECT
                fc.identifier AS identifier,
                fc.code AS code
            FROM friend_codes fc
            WHERE fc.user_id = %s
            ORDER BY fc.identifier ASC;
        """
        results = db.query(query, [ctx.author.id])
        db.close()

        # For every result returned, send an embed with the friend code and
        fields = []
        for result in results:
            fields.append((result['identifier'], result['code'], True))

        await ctx.send(embed = lib.embedder.make_embed(
            type = "info",
            title = f"F.C. List for {ctx.author.display_name}",
            fields = fields
        ))

    @friendcode_group.command(
        name = "listall",
        aliases = ["list_all"],
        brief = "Lists all the server's friend codes",
        description = "Cherubi Bot - Friend Code Sharing System",
        help = "Lists all friend codes for everyone on your server. This command is not mobile friendly"
    )
    @commands.check_any(commands.is_owner(), is_guild_owner())
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def listall_subcommand(self, ctx):
        # This MySQL statement is janky, but it works. Plus it is just an admin command, so it doesn't really matter
        db = mysql()
        query = """
            SELECT
                fc.user_id AS user_id,
                GROUP_CONCAT(CONCAT(fc.identifier, ': ', LPAD(fc.code, 12, '0')) SEPARATOR '\n') AS information
            FROM friend_codes fc
            LEFT JOIN user_preferences up ON up.user_id = fc.user_id
            WHERE up.home_guild = %s
            GROUP BY fc.user_id
            ORDER BY fc.identifier ASC;
        """
        results = db.query(query, [ctx.guild.id])
        db.close()

        # For every result returned, send an embed with the friend code and
        fields = []
        for result in results:
            # This is here in case someone leaves the guild, but it is still
            # set to their home guild
            if ctx.guild.get_member(result['user_id']):
                user_name = ctx.guild.get_member(result['user_id']).display_name
            else:
                user_name = self.client.get_user(result['user_id'])

            fields.append((user_name, result['information'], True))

        await ctx.send(embed = lib.embedder.make_embed(
            type = "info",
            title = f"F.C. List for {ctx.guild.name}",
            fields = fields
        ))

    @friendcode_group.command(
        name = "remove",
        aliases = ["r", "delete", "d"],
        brief = "Removes a friend code from your list.",
        description = "Cherubi Bot - Friend Code Sharing System",
        usage = "<trainer name>",
        help = "Removes the given friend code from your list"
    )
    async def remove_subcommand(self, ctx, identifier):
        db = mysql()
        query = """
            DELETE FROM friend_codes
            WHERE user_id = %s
            AND identifier = %s;
        """
        db.execute(query, [ctx.author.id, identifier])
        count = db.cursor.rowcount
        db.close()

        if count == 0:
            pass
            await ctx.send(embed = lib.embedder.make_embed(
                type = "error",
                title = f"Error Removing Friend Code",
                content = f"{identifier} not found on your list."
            ))

        else:
            await ctx.send(embed = lib.embedder.make_embed(
                type = "success",
                title = f"Removed Friend Code",
                content = f"Removed {identifier} from your list."
            ))

    @friendcode_group.command(
        name = "visibility",
        aliases = ["vis", "v"],
        brief = "Changes your friend code visibility.",
        description = "Cherubi Bot - Friend Code Sharing System",
        usage = "<public | private | hidden>",
        help = "This lets you change your visiblity to either public, private, or hidden depending what you want.\n\n\
            Public: lets anyone on any server you're in tag you and see your friend codes.\n\n\
            Private: lets only your home server see your friend codes.\n\n\
            Hidden: lets no one tag you to see your friend codes. You have to invoke !friendcode yourself for them to show."
    )
    async def visibility_subcommand(self, ctx, visibility = None):
        # If they don't give a visibility, tell them what their current setting is
        if not visibility:
            db = mysql()
            query = """
                SELECT fc_visibility
                FROM user_preferences
                WHERE user_id = %s;
            """
            results = db.query(query, [ctx.author.id])
            db.close()

            if not results:
                visibility = "private"
            else:
                visibility = results[0]['fc_visibility']

            await ctx.send(embed = lib.embedder.make_embed(
                type = "info",
                title = f"Your F.C. Visibility",
                content = f"Your friend code visibility is currently set to {visibility.title()}"
            ))
            return

        # Normalize it to all lowercase
        visibility = visibility.lower()

        # List of available visibility settings
        visibility_settings = ["public", "private", "hidden"]

        # Check if the given one is within the list. If not, spit out an error embed and return
        if visibility not in visibility_settings:
            await ctx.send(embed = lib.embedder.make_embed(
                type = "error",
                title = f"Error Changing F.C. Visibility",
                content = f"{visibility.title()} is not a valid option."
            ))
            return

        db = mysql()
        query = """
            INSERT INTO user_preferences (user_id, fc_visibility)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE fc_visibility = VALUES(fc_visibility);
        """
        db.execute(query, [ctx.author.id, visibility])
        db.close()

        await ctx.send(embed = lib.embedder.make_embed(
            type = "success",
            title = f"Changed F.C. Visibility",
            content = f"Changed your friend code visibility to `{visibility.title()}`."
        ))


def setup(client):
    client.add_cog(FriendCode(client))
