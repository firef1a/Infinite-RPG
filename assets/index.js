var ws = null;
var socket_uuid = null;
var current_game = false;
var can_sumbit_option = false;
var alevel = 1;

var button_list = []

function ws_send(event, data=null) {
  let msg = JSON.stringify({"event": event, "data": data})
  if (ws != null) {
    ws.send(msg);
    console.log(`client -> ${msg}`)
  } else {
    console.log("⚠️ ws not connected:", ws, msg)
  }
}

function startWebsocket() {
  ws = new WebSocket("ws://localhost:8001/websocket/");
  //ws = new WebSocket("wss://squaregame.qube-craft.com:443/websocket/");
  ws.onopen = function() {
    console.log("OPEN WS CONNECTION -------->")
  };

  ws.onmessage = function (evt) {
    let msg = JSON.parse(evt.data);
    event = msg['event']
    data = msg['data']
    console.log(evt.data);

    if (event == "on_connect") {
      ws_send("request_new_uuid", socket_uuid)
    }

    if (event == "new_uuid_response") {
      socket_uuid = data
      console.log("new uuid: " + socket_uuid)
      if (current_game == false) {
        ws_send("request_new_game", socket_uuid)
      }
    }

    if (event == "response_game_output") {
      alevel = alevel + 1;
      update_counter(2)
      var main_timeout = 0;
      if (current_game == false) {
        var loading_element = document.getElementById('loading')
        loading_element.classList.add("fade-out")
        main_timeout = 400;
        setTimeout(() => {
          loading_element.style.display = 'none';
        }, 600)

      }

      var message_list = data['message']
      var options_list = data['options']
      console.log(options_list)

      var message_content_div = document.getElementById('content')
      var options_div = document.getElementById('options')


      var content_timeout = 600

      if (current_game == false) {
        message_content_div.classList.add("fade-in")
        content_timeout = 0
      } else {
        message_content_div.classList.remove("fade-in")
        message_content_div.classList.add("fade-out")
      }

      setTimeout(() => {
        set_message_content_text = ""
        message_list.forEach((line) => {
          set_message_content_text = set_message_content_text + line
        })
        message_content_div.innerHTML = set_message_content_text
        message_content_div.classList.remove("fade-out")
        message_content_div.classList.add("fade-in")
      }, content_timeout)


      var options_timeout = 600

      if (current_game == false) {
        options_div.classList.add("fade-in")
        options_timeout = 0
      } else {
        options_div.classList.remove("fade-in")
        options_div.classList.add("fade-out")
      }

      
      
      setTimeout(() => {
        options_div.innerHTML = ""

        button_list = []

        options_list.forEach((option) => {
          let break_element = document.createElement("br");
          let button = document.createElement("button");
          button.classList.add("button-46")
          button.classList.add("fade-in");
          button.role = "button"
          button.innerHTML = option;

          button_list.push(button)


          // 2. Append somewhere
          options_div.appendChild(button);
          //options_div.appendChild(break_element)

          // 3. Add event handler
          button.addEventListener ("click", function() {
            if (can_sumbit_option) {
              let temp_content_element =document.getElementById('content');
              button_list.forEach((element) => {
                if (button != element) {
                  //element.style.visibility = 'hidden';
                  element.classList.remove("fade-in");
                  element.classList.add("fade-out");
                }
              })

              ws_send("send_game_input", option)
              can_sumbit_option = false;
            }
          });
        });
        options_div.classList.remove("fade-out")
        options_div.classList.add("fade-in")
      }, options_timeout)


      

      
      can_sumbit_option = true;
      current_game = true;
      
    }
    // ws_send("interaction_integer_request", "1")


  };

  ws.onclose = function(evt) {
    console.log("CLOSED WS CONNECTION <---------")
    //console.log("close");
    ws = null;
    setTimeout(startWebsocket, 500);
  };
}
startWebsocket()

function update_counter(le) {
  document.getElementById("level_counter").value = "Level #" + le
}

function setCookie(cname, cvalue, exdays) {
  const d = new Date();
  d.setTime(d.getTime() + (exdays * 24 * 60 * 60 * 1000));
  let expires = "expires="+d.toUTCString();
  document.cookie = cname + "=" + cvalue + ";" + expires + ";path=/";
}

function getCookie(cname) {
  let name = cname + "=";
  let ca = document.cookie.split(';');
  for(let i = 0; i < ca.length; i++) {
    let c = ca[i];
    while (c.charAt(0) == ' ') {
      c = c.substring(1);
    }
    if (c.indexOf(name) == 0) {
      return c.substring(name.length, c.length);
    }
  }
  return "";
}