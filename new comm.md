Lora is now a fully transparent bridge

It will expose an interface that looks like the robot (same udp endpoints, instead of robot:4300 it will be lora_steamdeck:4300)

These ports will be manually configured in a config file so the server knows what to listen and where to transfer.

When the steam deck lora server receives a packet on for example on port lora_steamdeck:4300, it will add either encapsualte the packet in another packet, or simply add to the data a topic id, so the target can differentiate.

It will then send that packet to the lora port. On the other side, that lora port will be sent to an equivalent server, it will read it, realize which ports is it meant to, and send it to robot:4300. Therefore, sending a packet to both robot:4300 and lora_steamdeck:4300 will end on the robot:4300 port. Thats the goal.

Of course this works both sides, with a packet received robot-side on lora_rove:5000 being sent to steam_deck:5000.

We must also hard limit the packet (or just payload) size, maybe to 230 byte, so it fits in the LoRa max 240 byte payload and gives us some headroom for id'ing (adding the target port).

