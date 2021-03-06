import { Injectable } from '@angular/core';
import { Http, Response, Headers, RequestOptions, URLSearchParams } from '@angular/http';
import 'rxjs/add/operator/map';
import 'rxjs/add/operator/catch';
import { Observable } from 'rxjs/Observable';
import { ReplaySubject } from 'rxjs/ReplaySubject';
import { Router } from '@angular/router';

import { MapService } from '../../../shared/maps/map.service'
import { NotificationService } from '../dashboard/notification-dash/notification.service.ts'
import { NotificationsService } from 'angular2-notifications'
import { FacilityService } from '../../../shakecast-admin/pages/facilities/facility.service.ts'

export interface Earthquake {
    shakecast_id: string;
    event_id: string;
    magnitude: number;
    depth: number;
    lat: number;
    lon: number;
    description: string;
    shakemaps: number;
}

@Injectable()
export class EarthquakeService {
    public earthquakeData = new ReplaySubject(1);
    public dataLoading = new ReplaySubject(1);
    public plotting = new ReplaySubject(1);
    public showScenarioSearch = new ReplaySubject(1);
    public filter = {};
    public configs: any = {clearOnPlot: 'all'};
    public selected: Earthquake = null;

    constructor(private _http: Http,
                private notService: NotificationService,
                private mapService: MapService,
                private facService: FacilityService,
                private _router: Router,
                private toastService: NotificationsService) {}

    getData(filter: any = {}) {
        this.dataLoading.next(true);
        let params = new URLSearchParams();
        params.set('filter', JSON.stringify(filter))
        this._http.get('/api/earthquake-data', {search: params})
            .map((result: Response) => result.json())
            .subscribe((result: any) => {
                this.earthquakeData.next(result.data);
                this.dataLoading.next(false);
            });
    }

    getDataFromWeb(filter: any = {}) {
        this.dataLoading.next(true);

        var usgs: string = 'https://earthquake.usgs.gov/fdsnws/event/1/query'

        filter['format'] = 'geojson'

        // get params from filter
        if (!filter['starttime']) {
            filter['starttime'] = '2005-01-01'
        }

        if (!filter['minmagnitude']) {
            filter['minmagnitude'] = '6'
        }

        let params = new URLSearchParams();
        for (var search in filter) {
            params.set(search, filter[search])
        }
        
        this._http.get(usgs, {search: params})
            .map((result: Response) => result.json())
            .subscribe((result: any) => {
                // convert from geoJSON to sc conventions
                var data = this.geoJsonToSc(result['features']);
                this.earthquakeData.next(data);
                this.dataLoading.next(false);
            });
    }

    downloadScenario(scenario_id: string) {
        this.dataLoading.next(true);
        this._http.get('/api/scenario-download/' + scenario_id)
            .map((result: Response) => result.json())
            .subscribe((result: any) => {
                this.toastService.success('Scenario: ' + scenario_id, 'Download starting...')
                this.dataLoading.next(false);
            });
    }

    deleteScenario(scenario_id: string) {
        this.dataLoading.next(true);
        this._http.delete('/api/scenario-delete/' + scenario_id)
            .map((result: Response) => result.json())
            .subscribe((result: any) => {
                this.toastService.success('Delete Scenario: ' + scenario_id, 'Deleting... This may take a moment')
                this.dataLoading.next(false);
            });
    }

    runScenario(scenario_id: string) {
        this._http.post('/api/scenario-run/' + scenario_id)
            .map((result: Response) => result.json())
            .subscribe((result: any) => {
                this.toastService.success('Run Scenario: ' + scenario_id, 'Running Scenario... This may take a moment')
                this.dataLoading.next(false);
            });
    }

    getFacilityData(facility: any) {
        this.dataLoading.next(true);
        this._http.get('/api/earthquake-data/facility/' + facility['shakecast_id'])
            .map((result: Response) => result.json())
            .subscribe((result: any) => {
                this.notService
                this.dataLoading.next(false);
            })
    }
    
    plotEq(eq: Earthquake) {
        if (eq) {
            this.notService.getNotifications(eq);
            this.plotting.next(eq);
            this.mapService.plotEq(eq, this.configs['clearOnPlot']);
        }

        if (this._router.url == '/shakecast/dashboard') {
            this.facService.getShakeMapData(eq);
        }

    }

    geoJsonToSc(geoJson: any[]) {
        // just add the fields we would expect from the shakecast 
        // database

        for (var eq_id in geoJson) {
            var eq = geoJson[eq_id]
            geoJson[eq_id]['shakecast_id'] = null;
            geoJson[eq_id]['event_id'] = eq['id'];
            geoJson[eq_id]['magnitude'] = eq['properties']['mag']
            geoJson[eq_id]['lon'] = eq['geometry']['coordinates'][0]
            geoJson[eq_id]['lat'] = eq['geometry']['coordinates'][1]
            geoJson[eq_id]['depth'] = eq['geometry']['coordinates'][2]
            geoJson[eq_id]['place'] = eq['properties']['place']

            if (eq['properties']['types'].indexOf('shakemap') > 0) {
                geoJson[eq_id]['shakemaps'] = 1
            } else {
                geoJson[eq_id]['shakemaps'] = 0
            }       
        }
        return geoJson
    }
}