#!/usr/bin/env python3

import os, sys, string, time, logging, math, argparse
from logging import debug,warning,info,error,fatal,critical; warn=warning

from bottle import route, run, template, static_file, get, Bottle, response, request, abort

from gevent import monkey; monkey.patch_all()
import requests
import datetime
import threading
import json
import collections
import uuid
import random

from gevent.pywsgi import WSGIServer
from geventwebsocket import WebSocketError
from geventwebsocket.handler import WebSocketHandler
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

#system_prompt_raw = 'Generate an intertwined simple rpg game with many branching paths, make sure to include puzzles that require exploration of other paths for information aswell. For the format, present the players current situation which should be no longer than a 20 words and try to keep it as concise as possible, then a list of numbers options, the number should be followed by an emoji related to the content of the following option. The number should be an actual number and not an emoji. Rarely include codes the player has to remembers for later or seperate portions of the map/game, like a maze or a lock but do NOT have memorizing the sequence or code as an option. The player should have to memeorize these codes outside of the game do not give them an option to memorize it. Never include an option to "commit to memory" or "memorize" parts of the story, for example if theres a code on a wall, do not give an option to memeorize it. Do not always include 4 answers, for paths include higher number of options and for straight forward actions include 1-2, try to provide less options unless neccesary. Do not include specific information when searching for items the player would not know are there. You may include wrong answers to puzzles. Do not have multiple rewards in the same area and do not have a puzzle and its answer in the same area. Do not include more exposition about the current situtation or add a title. Do not prompt the player to choose an option. the player will then pick a numbered object and you will continue based on that option and the story before it and repeat. do not tell the player to choose an option by typing a number or any other text. the player should have to option to go back to previous areas if the passage/action is not a one way action/passage. when returning to a previous area, if nothing substantial has occured to affect the area, present the same thing as the first time it was presented without any alterations. If the player dies, only include 1 option which revives them at the previous point. Do not include secret passages or hidden tunnels. Include dead ends from time to time. In addition, allow the player to win by obtaining the orb of true knowledge, which should be extremely difficult to obtain requiring multiple riddles and puzzles to be solves and the player to revisit multiple areas. options for riddles must include 2 or more answers to the riddle/puzzle. once a player wins, present only 1 option to restart the game and generate a story set in a dungeon.'
system_prompt_raw = 'Generate an intertwined simple rpg game with many branching paths, make sure to include puzzles that require exploration of other paths for information aswell. For the format, present the players current situation which should be no longer than a 20 words and try to keep it as concise as possible, then a list of numbers options, the number should be followed by an emoji related to the content of the following option. The number should be an actual number and not an emoji. Generate a random theme for the adventure anywhere from the range of a sci-fi adventure to a fantasy setting or a lit rpg dungeon crawler, come up with something random. Do not state the theme at the start'

system_prompt_json = { 'role': "system", 'content': system_prompt_raw }

env_key = os.environ.get("key")

client = OpenAI(
  api_key = env_key
)

class PServer(threading.Thread):
  def __init__(self, app):
    super(PServer, self).__init__()
    self.daemon = True
    self.app = app

  def run(self):
    n = 0
    while 1:
      n += 1
      if 1:
        pass
        print ("> tick %d" % n)
        self.app.broadcastMessage("tick", n)

      time.sleep(1)

class App(Bottle):
  def __init__(self):
    super(App, self).__init__()
    self.route('/', callback=self.index)
    self.route('/<filepath:path>', callback=self.server_static)
    self.route('/websocket/', callback=self.handle_websocket)

    self.workqueue = []

    self.sockets = []
    self.socket_uuids = {}
    self.socket_context = {}
        
  def index(self):
    return template("assets/index.html")

  def server_static(self, filepath):
    return static_file(filepath, root='assets/')

  def generate_uuid(self, prefix="", suffix=""):
    return f"{prefix}{str(uuid.uuid4())}{suffix}"

  def add_socket(self, wsock):
    self.sockets.append(wsock)
    
  def remove_socket(self, wsock):
    if wsock in self.socket_uuids:
      socket_uuid = self.socket_uuids[wsock]
      if socket_uuid in self.socket_context: 
        del self.socket_context[socket_uuid]
      del self.socket_uuids[wsock]

    if wsock in self.sockets: 
      self.sockets.remove(wsock)


  def sendMessage(self, wsock, event, data=None):
    msg = json.dumps({"event": event, "data": data})
    try:
      wsock.send(msg)
    except WebSocketError:
      self.remove_socket(wsock)

  def broadcastMessage(self, event, data=None):
    msg = json.dumps({"event": event, "data": data})
    for wsock in self.sockets:
      try:
        wsock.send(msg)
      except WebSocketError:
        self.remove_socket(wsock)

  def deep_copy(self, rlist):
    r = []
    for e in rlist:
      r.append(e)
    return r

  def leave_game(self, wsock):
    try:
      uuid = self.socket_uuids[wsock]
      if uuid in self.client_in_rooms.keys():
        room_uuid = self.client_in_rooms[uuid]
        room = self.game_rooms[room_uuid]
        players = room['players']

        keys = self.deep_copy(self.socket_uuids.keys())
        values = self.deep_copy(self.socket_uuids.values())

        for p in players:
          psocket = keys[values.index(p)]
          if psocket in self.sockets:
            if psocket != wsock:
              self.lobby_clients.append(psocket)
              self.sendMessage(psocket, "leave_game", f"The other player ({self.socket_usernames[self.socket_uuids[wsock]]}) left the match, so you were sent back to the lobby.")
          if self.client_in_rooms.get(p): self.client_in_rooms.pop(p)
        self.game_rooms.pop(room_uuid)
        self.update_lobby_list()
    except:
      if wsock in self.sockets: del self.sockets[wsock]
      
    #self.sendMessage(wsock, "update_lobby_list", send_list)

  def request_chatgpt(self, input_list):
    completion = client.chat.completions.create(
        model = "gpt-4o-mini",
        messages = input_list
    )

    response_message = completion.choices[0].message.content
    return response_message

  def parse_chatgpt_response(self, response_message):
    response_lines = response_message.split("\n")
    reversed_lines = response_lines[::-1]

    message_list = []
    option_list = []

    options = True
    spacer = True
    for line in reversed_lines:
      first_char = line[:1]

      if options:
        try:
          print (first_char)
          parsed_int_char = int(first_char)

          option_list.append(line[3:])
          if parsed_int_char == 1:
            options = False
        except:
          print ("ERROR PARSING")
      else:
        if spacer:
          spacer = False
        else:
          message_list.append(line.replace("**", ""))  
    corrected_option_list = option_list[::-1]
    return { 'message': message_list, 'options': corrected_option_list }


  def handle_websocket(self):
    wsock = request.environ.get('wsgi.websocket')
    if not wsock:
      abort(400, 'Expected WebSocket request.')

    self.add_socket(wsock)
    try:
      self.sendMessage(wsock, "on_connect")
      
      while True:
        try:
          message = wsock.receive()
          if message is None: break
          debug("Message: %s" % repr(message))
          
          message = json.loads(message)
          event = message.get('event')
          data = message.get('data')
          print (f"<WS> {event} {data}")

          if event == "request_new_uuid":
            if not wsock in self.socket_uuids.keys():
              old_uuid = data
              new_uuid = self.generate_uuid()
              self.sendMessage(wsock, "new_uuid_response", f"uuid-{new_uuid}")
              self.socket_uuids[wsock] = new_uuid
              if old_uuid in self.socket_context:
                self.socket_context[new_uuid] = self.socket_context[old_uuid]
                del self.socket_context[old_uuid]

          if event == "request_new_game":
            socket_uuid = self.socket_uuids[wsock]
            self.socket_context[socket_uuid] = [system_prompt_json]

            request_completion_messages = self.socket_context[socket_uuid]

            response_message = self.request_chatgpt(request_completion_messages)
            request_completion_messages.append({'role': "assistant", 'content': response_message})
            self.socket_context[socket_uuid] = request_completion_messages
            
            send_data = self.parse_chatgpt_response(response_message)
            self.sendMessage(wsock, "response_game_output", send_data)


          if event == "send_game_input":
            socket_uuid = self.socket_uuids[wsock]

            request_completion_messages = self.socket_context[socket_uuid]
            request_completion_messages.append({'role': "user", 'content': data})

            response_message = self.request_chatgpt(request_completion_messages)
            request_completion_messages.append({'role': "assistant", 'content': response_message})
            self.socket_context[socket_uuid] = request_completion_messages
            
            send_data = self.parse_chatgpt_response(response_message)
            self.sendMessage(wsock, "response_game_output", send_data)

        except WebSocketError:
          break

    finally:
      if wsock in self.sockets:
        self.remove_socket(wsock)
    
def application(environ, start_response):
  response_body = 'The request method was %s' % environ['REQUEST_METHOD']
  response_body = response_body.encode('utf-8')
  response_headers = [('Content-Type', 'text/plain'),
                      ('Content-Length', str(len(response_body)))]
  start_response('200 OK', response_headers)
  return [response_body]

def logger(func):
  def wrapper(*args, **kwargs):
    log = open('log.txt', 'a')
    log.write('%s %s %s %s %s \n' % (request.remote_addr, datetime.datetime.now().strftime('%H:%M'),
                                     request.method, request.url, response.status))
    log.close()
    req = func(*args, **kwargs)
    return req
  return wrapper

          
def start(args):
  open("server.pid", "w").write(str(os.getpid()))

  logging.info("Starting server")

  app = App()
  #app.loadState()
  
  pserver = PServer(app)
  pserver.start()
  
  app.install(logger)

  server = WSGIServer(("127.0.0.1", 8001), app, handler_class=WebSocketHandler)
  logging.info("Serving: %s:%s" % server.address)
  server.serve_forever()

def test():
  logging.warn("Testing")

def parse_args(argv):
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter, description=__doc__)

  parser.add_argument("-t", "--test", dest="test_flag", default=False, action="store_true", help="Run test function")
  parser.add_argument("--log-level", type=str, choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Desired console log level")
  parser.add_argument("-d", "--debug", dest="log_level", action="store_const", const="DEBUG", help="Activate debugging")
  parser.add_argument("-q", "--quiet", dest="log_level", action="store_const", const="CRITICAL", help="Quite mode")
  #parser.add_argument("files", type=str, nargs='*')

  args = parser.parse_args(argv[1:])

  return parser, args

def main(argv, stdout, environ):
  if sys.version_info < (3, 0): reload(sys); sys.setdefaultencoding('utf8')

  parser, args = parse_args(argv)

  if args.log_level is None: args.log_level = "INFO"

  logging.basicConfig(format="[%(asctime)s] %(levelname)-6s %(message)s (%(filename)s:%(lineno)d)", 
                      datefmt="%m/%d %H:%M:%S", level=args.log_level)

  if args.test_flag:  test();   return

  start(args)

if __name__ == "__main__":
  main(sys.argv, sys.stdout, os.environ)
