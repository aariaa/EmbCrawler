from __future__ import print_function
import requests
import pprint
from bs4 import BeautifulSoup
import urls
import regex
import config


class EmbCrawler():
    def __init__(self, userid, password):
        self.requests_sess = requests.Session()

        # Login the user into EMB
        # Note: The POST data has to be in the exact order (userid, password, login:Login) or else kohkt's script
        # returns 'Invalid login'
        # Note: There must be a referer in the headers, else kohkt's script gets confused and hangs
        post_data = [("userid", userid), ("password", password), ("login", "Login")]
        headers = {'referer': urls.login_page}
        response = self.requests_sess.post(url=urls.login_handler, data=post_data, headers=headers)

        # Check if the login was successful
        if "invalid login" in response.text.lower():  # check for invalid userid/password
            raise ValueError("Wrong userid or password")
        elif "prevented from login" in response.text.lower():  # check if user forgot to logout/has another emb session
            raise Exception("Prevented from login")
        else:
            print("Logged in")

        # Gets a list of boards the user has access to
        response = self.requests_sess.get(urls.boards_list)
        # Parse the returned html and iterate through all the links on the page
        # One of the link is for logging out while others are for accessing the boards
        soup = BeautifulSoup(response.text, 'html.parser')
        self.boards = {}
        for link in soup.find_all('a'):
            if not 'logout' in link.text.lower():
                # Determine the absolute href to the current board
                relative_link_to_board = link.get("href")
                l = urls.boards_list.split("/")[:-1]
                l.append(relative_link_to_board)
                abs_link_to_board = "/".join(l)
                self.boards[link.text.lower()] = abs_link_to_board

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Logout the user
        response = self.requests_sess.get(urls.logout_handler)

        # When a user logouts, he will be redirected to the login page his corresponding board
        # For example, <meta http-equiv="REFRESH" content="0;url=/smb/hs_student">
        # However, if the user is not logged in and tries to access the logout script, he will be redirected to the home page
        # i.e. <meta http-equiv="REFRESH" content="0;url=//">
        if "url=//" in response.text.lower():
            raise Exception("Tried to logout without logging in")

    def get_boards(self):
        return self.boards

    def get_messages(self, board_name):
        if board_name.lower() not in self.boards:
            raise ValueError("No such board/User has no access")

        # Login to specified board
        login_board_url = self.boards[board_name]
        response = self.requests_sess.get(login_board_url)

        # If the user is logged into a board and didn't logout, trying to login again will result in this error message
        # Note that it takes quite a long time for kohkt's script to return this error should it happen
        if "no such file or directory" in response.text.lower():
            # Logout of the board and retry
            self.requests_sess.get(urls.exit_board + "?" + board_name)
            return self.get_messages(board_name)

        # Once logged into a board, sending a GET request to the view board url will return the messages
        response = self.requests_sess.get(urls.view_board)
        # Parse the HTML
        html = response.text.encode("utf-8")
        soup = BeautifulSoup(html, 'html.parser')
        # Init empty list to store messages
        messages = []
        # Get a list of all table rows in the html document
        # We remove the first row as its the header, not actual content..
        rows = soup.find_all('tr')[1:]
        for row in rows:
            # As the raw html for each message is extremely, extremely, messy, we have to resort to regex magic
            # to extract the message's information
            cells = regex.findall(r'<td((.|\n)*?)<td', str(row), overlapped=True)
            # Init empty list to store the message's information
            info = []
            # We remove the first cell (effectively the first column) as it is not actual information (refer to EMB)
            for cell in cells[1:]:
                # We parse the html of the cell to extract the information in a string
                soup = BeautifulSoup("<td%s</td>" % (str(cell[0]),), 'html.parser')
                info.append(soup.text.strip())
            # Assign each information to its corresponding variable
            msg_date, msg_by, msg_title, msg_to, msg_num_reads = info
            # Init a EmbMessage object to store this message
            msg = EmbMessage(date=msg_date, by=msg_by, title=msg_title, to=msg_to, num_reads=msg_num_reads)

            messages.append(msg)

        # Logout of the board after we're done with it
        self.requests_sess.get(urls.exit_board + "?" + board_name)

        return messages


class EmbMessage():
    def __init__(self, by=None, to=None, date=None, title=None, body=None, num_reads=None):
        self.by = by
        self.to = to
        self.date = date
        self.title = title
        self.body = body
        self.num_reads = num_reads


if __name__ == "__main__":
    # Important to use 'with' keyword to ensure that EmbCrawler.__exit__() is invoked
    # The __exit__() function logs out the user from EMB
    with EmbCrawler(config.userid, config.password) as crawler:
        messages = crawler.get_messages('hs_student')
        for message in messages:
            print(message.title.encode('utf-8'))