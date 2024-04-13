# Home Assistant to Emotiva Processor Media Player


[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)


This custom component implements a media player entity and a remote entity for Home Assistant to allow for integration with Emotiva processors.  It's tested with the Emotiva XMC-1.  Given that I understand the Emotiva API is largely common across XMC-1, XMC-2 and RMC-1, it should work across these processors as well, but this is untested at present.

## Installation

The preferred installation approach is via Home Assistant Community Store - aka [HACS](https://hacs.xyz/).  The repo is installable as a [Custom Repo](https://hacs.xyz/docs/faq/custom_repositories) via HACS.

If you want to download the integration manually, create a new folder called emotiva under your custom_components folder in your config folder.  If the custom_components folder doesn't exist, create it first.  Once created, download the files and folders from the [github repo](https://github.com/peteS-UK/emotiva/tree/main/custom_components/emotiva) into this new emotiva folder.

Once downloaded either via HACS or manually, restart your Home Assistant server.

## Configuration

Configuration is done through the Home Assistant UI.  Once you're installed the integration, go into your Integrations (under Settings, Devices & Services), select Add Integration, and choose the Emotiva Processor integration.

This will display the configuration page.  

### Discover Processors
Checking the "Search for Emotiva Processors" option will ask the integration to search for processors during the setup process.  This uses udp broadcast, and so will only find processors on the same subnet as your Home Assistant server.  If discovery fails, or if your processors is on a different subnet, you can enter details manually.

### Manual Entry
You can enter the details of your processor manually by ticking "Enter details manually", and completing the fields.  At minumum, you must enter the IP Address and the Name of your processor.  Unless you know otherwise, you can likely leave the Control Port, Notification Port and Protocol to their default values.

When you select Submit, the configuration will discover the processor(s) and setup the components in Home Assistant.



## Usage

The integration add 3 services which can be included in automations, scripts etc., or called manually from Developer Tools/Services.

![image](https://github.com/peteS-UK/xmc/assets/64092177/b44b130e-f570-4365-b79d-6988130d2d64)

### Discover Emotiva Processor 

This service searches the local network for your processor.  The Home Assistant and processor must be on the same subnet.  Once found, the discovery process will update a number of attributes on the emotiva_xmc.processor entity for the processor.  Although you can run this manually, it's only really needed if you change something (e.g. the IP address of your processor).  Generally, the Send Command and Update States services will discover the processor when they're first run, and then use the saved states for future executions.

![image](https://github.com/peteS-UK/xmc/assets/64092177/080d56e6-3691-4064-ac5d-9a4cdb022d71)

### Send Command

This service allows you to send a command and its associated value to the processor.  It supports all 140 or so commands the Emotiva API supports.  Many commands take 0 as their value parameter (e.g. power_on).

![image](https://github.com/peteS-UK/xmc/assets/64092177/e9bc9bb1-f0fe-4ad0-bd0d-1762ce147078)

When you send a command, the attributes for emotiva_xmc.processor entity for the processor will also be updated.  You can use this in automations, scripts etc., or perhaps also from the HA API to allow you to use the Emotiva HA integration from other applications.

### Update States

When you discover, or send a command to the processor, it will update a number of entity attributes for the emotiva_xmc.processor entity.  Changes on the processor side aren't pushed to Home Assistant, so you should update the attributes before using them by calling this service.  You could of course setup a periodic automation to run, for example, once per minute, to keep these attributes fresh.

You could then, for example create triggers based on change of state

![image](https://github.com/peteS-UK/xmc/assets/64092177/6987142d-1bec-4602-953e-26a37948cf3e)

When you call the Update States service, by default it will create attributes for volume, power, mute, zone2 power, source, mode, audio_input, audio_bitstream, video_input &  video_format.  You can optionally specify any of the additional notification options from the processor, which will then create additional attributes in Home Assistant, which you can then monitor and use.

![image](https://github.com/peteS-UK/xmc/assets/64092177/05822950-efcc-435b-aa7f-22f0b17d10e1)








