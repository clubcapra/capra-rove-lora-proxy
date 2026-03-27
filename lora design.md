Design final propre:
Règles de base

1 message ROS = 1 paquet UDP, pis on prends linfo on la metes en byte en utilisant CDR de ros2
Timestamp check pour ejecter les paquets trop vieux
Pump continu ou delta selon le topic, aucun ack, aucun retry
No checksum; UDP basic checksum + CRC radio hardware du LoRa devraient suffire pour l'intégrité

Les 3 bools mergés en 1 paquet

system_state : estop + mh_enabled + vtx_enabled
4Hz constant, un seul topic_id, atomiquement cohérent, au lieu de send les 3 individuellement a 10hz chacun

Apres test

si manque encore de bandwith:
only send a message on state change for things such as estop and vtx/microhard enable/disable and estop. Keep sending state change notif until receiving ack from robot. robot will send one ack for every packet it receives, with an id to confirm its the same request.
send less telemetry I guess? we dont even know what were sendig yet

merge plus de topics/paquets ou reduire Hz si encore pas assez de bandwith

Si message arrivent malformes et passent:
CRC custom si la corruption passe les couches hardware plus souvent que prévu
HMAC+nonce sur les topics qui sont vraiment critiques (E-Stop)


ATTENDS, ENTRE LES LORA PAS UDP/TCP lora fait juste transmettre le contenu? fak aucune protectioncorruption a part whatever que les chinois on tmis?

NEWS:
ack system might be required for point(s) of interest. If so, will also be implemented for estop. Find a way to display async in UI? do a loading until we confirm the robot has acknowledged, or have a way to cancel?

note: on pourrait juste garder les points of interest client side et sync a la fin (via microhard ou manuellement)