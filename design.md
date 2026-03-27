First iteration of the design process of the communication system.
This is gonna be the broad strokes.

Definitions:
SD : This is the steam deck running Ubuntu 22.04
ROVE: This is Roboguard inside the robot.

VTX: 
1 emetteur et 1 recepteur
L'emetteur recoit une input 

MICROHEART:


LoRa:   

Red radio on channel 9, only legal one



///////////////////////
Results for testing

=====First device: FPV VTX
Quite simple. Once both are powered on channel 9 (do not forget antennas before power)

L'emetteur recoit un signal video via un cable HDMI, le Pi utilise donc ce cable comme si c'etait un simple moniteur.
Implications:
- Il faut que le programme soit capable de output la video en fullscreen a cet ecran lorsque 
- Il ne faut pas qun autre programme du Pi se mette devant. En fait, cela devrait etre fait dans sa propre session/terminal pour pas que les autres programmes aparaissent

Le recepteur fonctionne comme une simple webcam usb.
- Il faudra simplement que le UI soit capable de l'ouvrir as a widget dans son UI.

Requirement supplementaire: il faut tester, mais il se peut que le VTX overlap a exactement la moitie de la frequence du microhard. Donc il faudrait programmatiquement avoir sois l'un sois l'autre, ou tout simplement laisser l'operateur manuellement les turn off quand il voit de l'itnerference (ou quand le VTX est trop chaud).

======Test 2: LoRa
Client-Client TCP or other
Doc:
https://www.amxmotion.com/product/lora-eth/

So unfortunately we burned both so we will have to 100% design from the doc. THe ideal would be to have a layer that makes them both transparent in the end, so from a software design we can use it just like the microhard.

Note supplementaire:
Le lora commence a fausser le data quand la connexion est mauvaise.

======Test 3: MicroHard
These two devices work in full transparency, as an ethernet cable would. Simply assign a static IP to both device's ethernet port and they will be able to communicate in full duplex.

================
User saga, du point de vue steam deck

Le LoRa est toujours on.

On prevois qu'il serve a:
- Envoyer les commandes
- Recevoir la telemetrie ultra importante  et low bandwith only (position GPS et orientation 3d, temperature(s), voltage batterie, Estop state)
La liste exacte de quels topics sont envoye et recu est modulaire via un fichier de config. 1 topic ROS = 1 endpoint TCP.

Je ne pense pas quon a besoin de enforce que les deux config soient parfaitement good au demarrage. Si les topics ont un fuckup, ca a juste faire en sorte que certains topics se font pas send, ou quils se font pas lire.

Donc on force pas un checksum sur les deux fichier, mais on ajoutera un endpoint qui permet de renvoyer la config de l'autre. Cela permettra dimplementer des checks et warning dans le code plus tard

Pour eviter les problemes de perte de connexion dans le contexte de communicatio full duplex, UDP serait better surtout en cas de disconnect ou on veut juste pomper de linfo meme si la connectino drop et revient. mais comment s'assurer que le message est valide? comment s'assurer que le estop command est valide? on veut pas un faut estop ou une fausse commende d'acceleration genre. faudrait notre propre checksum, mais il faudrait quil soit vraiment basse latence pour pas rajouter plus de latence qui sera deja high. C++?

setups topic ros, it has 2 modes:
- if you fail to receive, retry
- if you fail to receive, dont care
Il faudra choisir lequel est plus approprie.

De plus, il y aura 4 toggles via LoRa
1. Toggle MicroHard video (pour plus de bande passante au nuage de point)
2. Toggle MicoHard nuage de points (pour plus de bande passante a video)
Toggle both above pour plus de bande passante a la telemetrie
3. Toggle entire MicroHard pour pas inteferer avec le VTX
4. Toggle VTX pour pas interferer avec le microhard (ou pour cool down)
Tout les toggle sont manuels. C'est l'operateur qui decide ce qui est necessaire.

Dans la config:
- What is published LorA
- What is listened lora
- what is published microhard
(no need to speicfy what to listen to on microhard, cest full transparent so nothing has to be listening unlike the lora tcp server)

Le microhard fonctionne en full transparence, comme un simple cable ethernet. Donc, ce sera plus facile: les topics ros sont tout simplement shared. Pour eviter de saturer, on voudrais quand meme controller ce que cette interface envoie/recoit:
on va diviser en 3 groupes, video, nuage de points, et telemetrie. Ce sera plus facile pour handle les toggles mentionnes ci haut.
Nuage de points cest un topic ros, telemetrie cest dautre topic ros. donc cest encore unfichier de config.
Pour la redondance, microhard recoit et envoie aussi les meme infos que lora (joy, orientatino, etc). Le robot pourra choisir la source.

VTX:
Le vtx ne requiert quasiement pas de code, il est tres dumb. However, il faudrat quand meme:
s'assurer quon envoie la video de la camera rtsp comme une output display. Comment faire si le pi est headless? yatil une librairie pour nous aider a faire ca. sans avoir a actually spin up un desktop pi? genre juste stream video>output sur un monitor, sans avoir de desktop?

faut aussi juste pouvoir le turn on and off. mais ca cest out of scope for now. Oublions le VTX pour linstant

RIGHT NOW: le focus, c'est de reussir a avoir 2 channels de communication standardisee (juste avec une config de ros topics et les actual topics, on fera un programme ultra simple qui les simule.) On veut juste avoir 2 channels standardisees, et apres je designerait du code qui decide quoi send quand, quoi shutdown quand.

Quen penses tu? as tu des idees de design et tech choices?


reddit:
LoRa modulation theoretically could do so, but performance would be terrible.

If you need TCP/IP type capabilities, you're probably looking at either a line of sight microwave link, or buying service from a mobile phone or even satellite provider. 

 In theory it can, I have yet to see a project which attempts it.

Pragmatically, it would be AWFUL IP. The bandwidth are tiny, like worse than 300 baud modem bad. If you really feel you need IP, then you should find a different solution. 

Conclusion: absolutely use UDP. for things that you cannot afford ot fuckup (disable/enable vtx, disable/enable microhard, estop) find a solution to reliably signal it via UDP. with a hash maybe. because now the logic flips: no commands doesnt mean lost conncetion, it just means no commands sent. we need a different, consistent heartbeat setup. and the estop shouldnt be destructive: if estop engaged, wait for confirmation of disengaged (and make sure both are valid with hash and not a result of data corurption)