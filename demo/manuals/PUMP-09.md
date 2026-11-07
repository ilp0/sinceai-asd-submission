# Cooling-tower circulation pump CW-2 and drive motor — Operation and maintenance manual

Asset: PUMP-09 · Plant C (food processing, fictional) · Cooling-tower water circuit · Document CW-02-OM, revision B

Demo document. The team wrote this manual for the RETROFIT AI demo from the organizer asset data. It is not a manufacturer document. Do not use it on a real installation.

## 1 Pump and motor data

1.1 The pump is a single-stage, end-suction centrifugal pump with a six-vane closed impeller. It circulates water from the cooling-tower basin to the process heat exchangers.
1.2 Rated duty point: 320 m³/h at 33 m head. Shut-off head: 39.6 m. Best-efficiency point efficiency: 81 %. Design point of the system: 300 m³/h at 32 m.
1.3 Required suction head (NPSH3) at the best-efficiency point: 3.4 m.
1.4 The drive motor is a 45 kW, 400 V, 50 Hz induction motor. Rated current: 79.9 A. Rated speed: 1480 rpm.
1.5 The pump runs at fixed speed with a direct-on-line starter. There is no speed control. The flow changes with the system resistance.
1.6 Bearings: deep-groove ball bearings, type 6311, grease lubricated. The fluid is treated cooling-tower water.
1.7 Pump CW-1 is the standby pump of the same circuit.

## 2 Safety

2.1 Before you open the pump, the strainer or a pipe, stop the pump and lock out the motor supply at the motor control centre. Attach a personal lock and tag.
2.2 Close and lock the suction and discharge valves. Release the pressure through the drain valve and make sure that the pressure gauge shows zero.
2.3 The cooling-tower water contains treatment chemicals. Wear gloves and eye protection when you drain or open the pump.
2.4 Do not start the pump with the discharge valve closed. Do not run the pump dry.
2.5 Do not bypass, disable or change a protective trip. The vibration trip, the winding-temperature trip and the motor protection stay active at all times.
2.6 Before a planned stop of this pump, the shift supervisor starts the standby pump (see section 15) and confirms the cooling of the process.
2.7 Do not put your hands near the coupling or the shaft while the motor can start.

## 3 Operating limits

3.1 Vibration velocity (RMS, 10–1000 Hz) on the bearing housing: alarm at 6.4 mm/s, trip at 10.6 mm/s.
3.2 Bearing temperature: alarm at 85 °C, trip at 95 °C. A rise of more than 10 °C above the normal value at the same load needs an investigation.
3.3 Motor winding temperature (insulation class F): alarm at 130 °C, trip at 145 °C.
3.4 Motor current: do not run continuously above the rated current of 79.9 A.
3.5 Flow: normal operation is 250 to 340 m³/h. Do not operate below 100 m³/h for more than 10 minutes.
3.6 Suction pressure: a decrease of more than 15 % from the normal value shows a suction-side restriction or a low basin level.

## 4 Condition monitoring and alerts

4.1 The retrofit monitoring system reads the pump and motor signals once per second.
4.2 The fault model gives one probability for each fault type. An alert starts when a probability stays at or above 0.9 for 15 minutes.
4.3 An alert tells you which fault is probable. It does not tell you the severity or the remaining life. Confirm the fault with the checks of the applicable section before you do corrective work.
4.4 When an alert is about a sensor fault, compare the sensor value with an independent measurement before you trust or ignore other alerts from that sensor.
4.5 Record each alert, the checks that you did and the result in the maintenance system.
4.6 Escalation: call the maintenance manager and change over to the standby pump (section 15) when a measured value reaches an alarm limit of section 3, or when the checks confirm a fault that you cannot correct during operation.

## 5 Suction strainer

5.1 A basket strainer is installed between the cooling-tower basin outlet and the pump. The basket mesh is 4 mm.
5.2 Symptoms of a clogged strainer: suction pressure decreases, the pressure difference across the strainer increases and the flow decreases.
5.3 Clean the basket when the pressure difference across the strainer is more than 15 kPa.
5.4 To clean the strainer, start the standby pump (section 15), stop and isolate this pump (2.1 and 2.2), then open the strainer cover.
5.5 Remove the basket, clean it with water and examine the mesh for holes. Replace a damaged basket.
5.6 After you clean the strainer, make sure that the suction pressure and the flow go back to the normal values.

## 6 Cavitation and suction conditions

6.1 Cavitation occurs when the suction pressure is too low for the flow. Symptoms: a noise like gravel in the pump, irregular vibration, an unstable discharge pressure and a decrease of head.
6.2 First examine the suction side: the basin water level, the strainer (section 5) and the suction valve position.
6.3 Keep the basin level above the minimum mark. Do not close the discharge valve to stop cavitation.
6.4 After a cavitation period of more than 24 hours, examine the impeller at the next planned stop (see section 11).

## 7 Discharge-side restriction

7.1 A partly closed valve, a fouled heat exchanger or a blocked pipe on the discharge side decreases the flow and increases the discharge pressure. At fixed speed, the motor power decreases when the flow decreases.
7.2 Check the positions of all discharge-side valves against the circuit diagram. Do not change a valve position before you know why it is in that position.
7.3 Check the pressure difference across the process heat exchangers. A difference above the value on the exchanger data plate shows fouling.
7.4 Clean a fouled heat exchanger according to its manual. Isolate it first (see 2.1 and 2.2).
7.5 After the correction, make sure that the flow, the discharge pressure and the motor power go back to the normal values.
7.6 If the flow is below 100 m³/h (3.5) and you cannot find the cause, start the standby pump and stop this pump.

## 8 Bearings

8.1 The pump has two 6311 deep-groove ball bearings. The drive-end bearing takes the radial load and the non-drive-end bearing takes the axial load.
8.2 Bearing wear shows first as an increase of the high-frequency vibration (acceleration and crest factor). The vibration velocity and the bearing temperature increase later.
8.3 When bearing wear is probable, measure the vibration velocity and acceleration on both bearing housings with a hand-held meter. Compare with the previous measurements.
8.4 Lubricate each bearing with 20 g of lithium-complex grease every 2000 running hours. Do not over-grease, because the temperature increases.
8.5 If the vibration velocity is above the alarm value (3.1) or the bearing temperature increases by more than 10 °C, plan a bearing replacement at the next possible stop.
8.6 Replace the bearings as a pair. Use an induction heater to install a bearing. Do not hit a bearing with a hammer.
8.7 After the replacement, run the pump for 2 hours and record the vibration and the bearing temperature.

## 9 Alignment and coupling

9.1 The pump and motor are connected with a flexible jaw coupling. Misalignment causes vibration at one and two times the running speed, increases the bearing temperatures and can increase the motor power and the winding temperature.
9.2 When misalignment is probable, measure the vibration on the motor and pump bearings in the horizontal, vertical and axial directions. A high axial vibration supports misalignment.
9.3 Check the alignment with a laser alignment tool. Permitted misalignment: 0.05 mm parallel offset and 0.05 mm/100 mm angular.
9.4 Examine the coupling element for wear and the foundation bolts for correct torque (120 N·m). Check for a soft foot under the motor feet.
9.5 Do the alignment only with the motor locked out (see 2.1 and 2.7).
9.6 After the alignment, run the pump for 1 hour and make sure that the vibration and the bearing temperatures decrease.

## 10 Impeller balance

10.1 Imbalance causes vibration at one times the running speed in the radial direction.
10.2 Causes: scale or deposits on the impeller, a damaged vane, or a loose part on the shaft.
10.3 Examine and clean the impeller at the next planned stop. Balance the impeller to grade G6.3 after a repair.

## 11 Impeller wear and internal clearances

11.1 Wear of the impeller and the wear rings decreases the head and the flow at fixed speed.
11.2 Compare the flow and the differential pressure with the pump curve. A decrease of head of more than 10 % at the same flow shows internal wear.
11.3 Replace the wear rings when the diametral clearance is more than 0.9 mm.

## 12 Air entrainment and priming

12.1 Air in the water decreases the head and makes the flow and the discharge pressure unstable. The motor power decreases and becomes irregular.
12.2 Causes: a low basin level that makes a vortex at the outlet, a leak in the suction pipe, or a foam problem in the basin.
12.3 Make sure that the basin level is above the minimum mark and that the make-up water valve operates.
12.4 Vent the pump casing through the vent cock. If the pump loses its prime, stop the pump and start the standby pump (section 15).

## 13 Instrumentation

13.1 Each sensor has a tag. Pressure transmitters and the flow meter have an accuracy of ±0.5 % of range. The temperature sensors have an accuracy of ±1 °C.
13.2 Sensor drift: the value moves slowly away from the true value. Calibration shift: the value changes suddenly by a fixed offset. A stuck sensor shows the same value for a long time. Noise spikes are short, large changes that the process cannot cause.
13.3 To check a sensor, compare its value with a local gauge, a hand-held instrument or a related signal. For example, compare the motor current with a clamp meter, and the bearing temperature with an infrared thermometer.
13.4 If a sensor is wrong, mark it as faulty in the monitoring system so that the model and the operators do not use its value. Do not disable a trip that uses the sensor without permission of the maintenance manager.
13.5 Recalibrate or replace a faulty sensor at the next possible time. Record the before and after values.
13.6 Until the sensor is repaired, read the local gauge each shift and write the value in the shift log.

## 14 Communication and gateway

14.1 The sensor gateway sends the data to the monitoring server. When the data stop, the dashboard shows a communication alert.
14.2 A communication loss does not mean that the pump has a fault. Check the pump locally: noise, vibration by hand, the local gauges and the motor current on the starter panel.
14.3 Check the gateway power and the network cable. Restart the gateway if its status light is red.
14.4 Until the data come back, do local rounds every 2 hours and record the values.

## 15 Standby pump changeover

15.1 Start the standby pump CW-1 from the local panel and wait until its discharge pressure is stable.
15.2 Make sure that the process cooling-water temperature stays within its limits for 5 minutes.
15.3 Then stop pump CW-2 and isolate it for the work (see 2.1 and 2.2).
15.4 After the work, return pump CW-2 to service according to the duty plan.
