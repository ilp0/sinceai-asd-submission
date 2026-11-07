# Seawater cooling pump No. 2 and drive motor — Operation and maintenance manual

Asset: PUMP-08 · Vessel B (RoPax, fictional) · Seawater cooling system · Document SWC-02-OM, revision C

Demo document. The team wrote this manual for the RETROFIT AI demo from the organizer asset data. It is not a manufacturer document. Do not use it on a real installation.

## 1 Pump and motor data

1.1 The pump is a single-stage, end-suction centrifugal pump with a six-vane closed impeller. It supplies seawater to the central coolers.
1.2 Rated duty point: 650 m³/h at 24 m head. Shut-off head: 29.3 m. Best-efficiency point efficiency: 83 %. Design point of the system: 620 m³/h at 23.5 m.
1.3 Required suction head (NPSH3) at the best-efficiency point: 4.6 m.
1.4 The drive motor is a 75 kW, 440 V, 60 Hz induction motor. Rated current: 119.8 A. Rated speed: 1785 rpm.
1.5 A variable-frequency drive (VFD) controls the motor speed to keep the cooling-water temperature at the set point. The minimum speed is 60 % of the rated speed (approximately 1070 rpm).
1.6 Bearings: deep-groove ball bearings, type 6312, grease lubricated. The fluid is brackish seawater (approximately 6 PSU).
1.7 Pump No. 1 is the standby pump of the same system.

## 2 Safety

2.1 Before you open the pump, the strainer or a pipe, stop the pump and lock out the motor supply at the main switchboard. Attach a personal lock and tag.
2.2 Close and lock the suction and discharge valves. Release the pressure through the drain valve and make sure that the pressure gauge shows zero.
2.3 This pump is connected to the sea. Before you open any part below the waterline, make sure that the sea-suction valve is closed and holds. Keep a blank flange and a bilge pump ready.
2.4 Do not start the pump with the discharge valve closed. Do not run the pump dry.
2.5 Do not bypass, disable or change a protective trip. The vibration trip and the motor protection stay active at all times.
2.6 Before a planned stop of this pump, the duty engineer starts the standby pump (see section 15) and confirms the cooling-water supply.
2.7 Do not put your hands near the coupling or the shaft while the motor can start.

## 3 Operating limits

3.1 Vibration velocity (RMS, 10–1000 Hz) on the bearing housing: alarm at 5.0 mm/s, trip at 8.3 mm/s.
3.2 Bearing temperature: alarm at 80 °C, trip at 90 °C. A rise of more than 10 °C above the normal value at the same load needs an investigation.
3.3 Motor current: do not run continuously above the rated current of 119.8 A.
3.4 Suction pressure: a decrease of more than 15 % from the normal value at the same speed shows a suction-side restriction. Do not operate below 20 kPa(g) suction pressure, because cavitation can start.
3.5 Do not operate below 30 % of the rated flow for more than 10 minutes, because the pump heats the water and the bearings get high loads.
3.6 Normal values change with the speed. Compare a measurement with the normal value at the same speed and the same operating mode.

## 4 Condition monitoring and alerts

4.1 The retrofit monitoring system reads the pump and motor signals once per second. The wireless vibration and bearing-temperature sensors send a value every 300 seconds.
4.2 The fault model gives one probability for each fault type. An alert starts when a probability stays at or above 0.9 for 15 minutes.
4.3 An alert tells you which fault is probable. It does not tell you the severity or the remaining life. Confirm the fault with the checks of the applicable section before you do corrective work.
4.4 When an alert is about a sensor fault, compare the sensor value with an independent measurement before you trust or ignore other alerts from that sensor.
4.5 Record each alert, the checks that you did and the result in the engine-room log.
4.6 Escalation: call the chief engineer and change over to the standby pump (section 15) when a measured value reaches an alarm limit of section 3, or when the checks confirm a fault that you cannot correct during operation.

## 5 Suction strainer

5.1 A duplex basket strainer is installed in the suction line between the sea chest and the pump. The basket mesh is 6 mm.
5.2 Symptoms of a clogged strainer: suction pressure decreases, the pressure difference across the strainer increases, and the VFD increases the speed to keep the cooling. Motor power can increase at the same cooling load.
5.3 Check the pressure difference across the strainer on the local gauge. Clean the basket when the difference is more than 20 kPa, or when the suction pressure is more than 15 % below the normal value at the same speed.
5.4 To clean the strainer during operation, change over to the clean basket with the changeover lever. Then isolate, drain and open the clogged side (see 2.1 to 2.3 for the isolated side).
5.5 Remove the basket, clean it with fresh water and examine the mesh for holes. Replace a damaged basket.
5.6 After you clean the strainer, make sure that the suction pressure and the speed of the pump go back to the normal values.
5.7 If the strainer clogs again within 24 hours, examine the sea chest grating for marine growth or debris.

## 6 Cavitation and suction conditions

6.1 Cavitation occurs when the suction pressure is too low for the flow. Symptoms: a noise like gravel in the pump, irregular vibration, an unstable discharge pressure and a decrease of head.
6.2 First examine the suction side: the strainer (section 5), the suction valve position and the sea-chest inlet.
6.3 Reduce the flow demand if the operating instructions of the vessel permit it. Do not close the discharge valve to stop cavitation.
6.4 Continued cavitation damages the impeller. After a cavitation period of more than 24 hours, examine the impeller at the next planned stop (see section 11).

## 7 Discharge-side restriction

7.1 A partly closed valve, a fouled cooler or a blocked pipe on the discharge side decreases the flow and increases the discharge pressure at the same speed.
7.2 Check the positions of all discharge-side valves against the system diagram. Do not change a valve position before you know why it is in that position.
7.3 Check the pressure difference across the central coolers. A difference above the value on the cooler data plate shows a fouled cooler.
7.4 Clean a fouled cooler according to the cooler manual. Isolate it first (see 2.1 to 2.3).
7.5 After the correction, make sure that the flow, the discharge pressure and the motor current go back to the normal values.

## 8 Bearings

8.1 The pump has two 6312 deep-groove ball bearings. The drive-end bearing takes the radial load and the non-drive-end bearing takes the axial load.
8.2 Bearing wear shows first as an increase of the high-frequency vibration (acceleration and crest factor). The vibration velocity and the bearing temperature increase later.
8.3 When bearing wear is probable, measure the vibration velocity and acceleration on both bearing housings with a hand-held meter. Compare with the previous measurements in the log.
8.4 Lubricate each bearing with 25 g of lithium-complex grease every 2000 running hours. Do not over-grease, because the temperature increases.
8.5 If the vibration velocity is above the alarm value (3.1) or the bearing temperature increases by more than 10 °C, plan a bearing replacement at the next possible stop.
8.6 Replace the bearings as a pair. Use an induction heater to install a bearing. Do not hit a bearing with a hammer.
8.7 After the replacement, run the pump for 2 hours and record the vibration and the bearing temperature.

## 9 Alignment and coupling

9.1 The pump and motor are connected with a flexible disc coupling. Misalignment causes vibration at one and two times the running speed and increases the bearing temperatures.
9.2 Check the alignment with a laser alignment tool after each bearing replacement, after work on the foundation and when the vibration at two times the running speed increases.
9.3 Permitted misalignment: 0.05 mm parallel offset and 0.05 mm/100 mm angular.
9.4 Examine the coupling discs for cracks and the foundation bolts for correct torque (180 N·m).
9.5 Do the alignment only with the motor locked out (see 2.1 and 2.7).

## 10 Impeller balance

10.1 Imbalance causes vibration at one times the running speed. The vibration increases with the speed.
10.2 Causes: marine growth or deposits on the impeller, a damaged vane, or a loose part on the shaft.
10.3 Examine and clean the impeller at the next planned stop. Balance the impeller to grade G6.3 after a repair.

## 11 Impeller wear and internal clearances

11.1 Wear of the impeller and the wear rings decreases the head and the flow at the same speed. The VFD increases the speed to compensate.
11.2 Compare the discharge pressure and the motor speed with the values at commissioning. A decrease of head of more than 10 % at the same speed shows internal wear.
11.3 Replace the wear rings when the diametral clearance is more than 1.0 mm.

## 12 Air entrainment and priming

12.1 Air in the seawater decreases the head and makes the flow and the discharge pressure unstable. The motor current decreases and becomes irregular.
12.2 Causes: low sea-chest water level in heavy weather, a leak in the suction pipe above the waterline, or a vent valve that is open.
12.3 Vent the pump casing through the vent cock. Make sure that the sea-chest vent pipe is open and clear.
12.4 If the pump loses its prime, stop the pump and start the standby pump (section 15). Do not run the pump dry (2.4).

## 13 Instrumentation

13.1 Each sensor has a tag. Pressure transmitters have an accuracy of ±0.5 % of range. The wireless temperature sensors have an accuracy of ±1 °C.
13.2 Sensor drift: the value moves slowly away from the true value. Calibration shift: the value changes suddenly by a fixed offset. A stuck sensor shows the same value for a long time. Noise spikes are short, large changes that the process cannot cause.
13.3 To check a sensor, compare its value with a local gauge, a hand-held instrument or a related signal. For example, compare the bearing temperature with an infrared thermometer.
13.4 If a sensor is wrong, mark it as faulty in the monitoring system so that the model and the operators do not use its value. Do not disable a trip that uses the sensor without permission of the chief engineer.
13.5 Recalibrate or replace a faulty sensor at the next possible time. Record the before and after values.
13.6 Until the sensor is repaired, read the local gauge each watch and write the value in the log.

## 14 Communication and gateway

14.1 The sensor gateway sends the data to the monitoring server. When the data stop, the dashboard shows a communication alert.
14.2 A communication loss does not mean that the pump has a fault. Check the pump locally: noise, vibration by hand, the local gauges and the motor current on the starter panel.
14.3 Check the gateway power and the network cable. Restart the gateway if its status light is red.
14.4 Until the data come back, do local rounds every 2 hours and record the values.

## 15 Standby pump changeover

15.1 Start the standby pump No. 1 from the local panel and wait until its discharge pressure is stable.
15.2 Make sure that the cooling-water temperature stays within the set-point band for 5 minutes.
15.3 Then stop pump No. 2 and isolate it for the work (see 2.1 to 2.3).
15.4 After the work, return pump No. 2 to service and keep it on standby or in operation according to the duty plan.
