# Home Assistant to Emotiva Processor Media Player


[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![maintained](https://img.shields.io/maintenance/yes/2025.svg)](#)
[![maintainer](https://img.shields.io/badge/maintainer-%20%40petes--UK-blue.svg)](#)
[![version](https://img.shields.io/github/v/release/peteS-UK/emotiva)](#)


This custom component implements a media player entity, a remote entity and a number of sensors for Home Assistant to allow for integration with Emotiva processors.  It was written for the Emotiva XMC-1 but now also been tested with XMC-2 and RMC-1 and works generally fine.  There are some limitiations with the XMC-2 and RMC-1 where the published API doesn't support some functions on these devices.  This includes the ability to switch between speaker presets/Dirac etc., where the API only supports the XMC-1 preset design and Emotiva currently have no plans to update the API in this area for the Gen 3 processors.

The integration is a Local Push integration - i.e. it subscribes to notification of changes to the processor, so doesn't need to periodically poll the processor for its state.

## Installation

The preferred installation approach is via Home Assistant Community Store - aka [HACS](https://hacs.xyz/).  

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=peteS-UK&repository=emotiva&category=integration)

If you want to download the integration manually, create a new folder called emotiva under your custom_components folder in your config folder.  If the custom_components folder doesn't exist, create it first.  Once created, download the files and folders from the [github repo](https://github.com/peteS-UK/emotiva/tree/main/custom_components/emotiva) into this new emotiva folder.

Once downloaded either via HACS or manually, restart your Home Assistant server.

## Configuration

Configuration is done through the Home Assistant UI.  Once you're installed the integration, go into your Integrations (under Settings, Devices & Services), select Add Integration, and choose the Emotiva Processor integration, or click the shortcut button below (requires My Homeassistant configured).

[![Add Integration to your Home Assistant
instance.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=emotiva)


This will display the configuration page.  

![image](https://github.com/user-attachments/assets/eabfad32-22b2-437b-9afa-8ff89648d730)


### Discover Processors
Checking the "Search for Emotiva Processors" option will ask the integration to search for processors each time your restart Home Assistant or reload the integration.  This uses udp broadcast, and so will normally only find processors on the same subnet as your Home Assistant server.  If discovery fails, or if your processors is on a different subnet, you can enter details manually.

### Manual Entry
You can enter the details of your processor manually by ticking "Enter details manually", and completing the fields.  At minumum, you must enter the IP Address and the Name of your processor.  Unless you know otherwise, you can likely leave the Control Port, Notification Port and Protocol to their default values.

![image](https://github.com/user-attachments/assets/0e10c430-0720-424a-b1f4-355fb45446e1)


When you select Submit, the configuration will discover the processor(s) and setup the components in Home Assistant.  It will create one device, nine entities and an action.

## Device & Entities
A device will be created with the same name as your processor - e.g. XMC-1.

![image](https://github.com/user-attachments/assets/0cd9483d-0f5b-40b1-ab20-782e745aa398)

### Media Player entity
A media player entity will be created with a default entity_id of media_player.emotivaprocessor.  


![image](https://github.com/peteS-UK/emotiva/assets/64092177/1e90c014-3b1f-4b1e-9f04-e24b7a3bdfb9)


You can control power state, volume, muting, source and sound mode from the media player.  You can also use this entity from any card for media player.

### Remote Entity & Action
The remote entity allows you to control power, but is primarily included so that you can send commands directly to the Emotiva processor using the remote.send_command service.


![image](https://github.com/peteS-UK/emotiva/assets/64092177/a8934369-89e2-422a-ae37-5ae742e980af)


The command must be entered as command_name,value e.g. **power_on,0**.  The details for the commands can be found in Emotiva's API documentation.  More simply though, you can use the emotiva.send_command service, which provides a drop down of the available options.

## Emotiva Processor. Send Command

The integration provides a service which allows you to send any command to the processor, similar to the remote.send_command service.  However, this service provides you with a dropdown list of all of the available commands, and formats the command string for you.


![image](https://github.com/peteS-UK/emotiva/assets/64092177/1e41cc49-a5a3-4922-bd37-1903eb1ca722)


### Media Player States

The integration tracks the the state of volume, power, mute, zone2 power, source, mode, audio_input, audio_bitstream, video_input &  video_format on the processor and creates and maintains attributes on the media_player.emotivaprocessor entity.


![image](https://github.com/peteS-UK/emotiva/assets/64092177/55480ee9-705c-4904-a916-1b7b99e74ee5)


You could then use these attributes to trigger an automation based on a change of state, for example when the source is changed to "Oppo"


![image](https://github.com/peteS-UK/emotiva/assets/64092177/290519fc-c5d3-4ae2-9436-2206d17c3572)


You can also Configure the entity to track additional notifications from the processor.  In your Integration page, select Configure, and enter a list of comma seperated notifications for which the integration should create additional state attributes.


![image](https://github.com/peteS-UK/emotiva/assets/64092177/f106ce12-5110-490f-a5c3-3c15d74f8163)






