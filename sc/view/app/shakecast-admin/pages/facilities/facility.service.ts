import { Injectable } from '@angular/core';
import { Http, Response, Headers, RequestOptions, URLSearchParams } from '@angular/http';
import 'rxjs/add/operator/map';
import 'rxjs/add/operator/catch';
import { Observable } from 'rxjs/Observable';
import { ReplaySubject } from 'rxjs/ReplaySubject';

import { MapService } from '../../../shared/maps/map.service'

export interface Facility {
    shakecast_id: string;
    facility_id: string;
    lat: number;
    lon: number;
    name: string;
    description: string;
    selected?:boolean
}

@Injectable()
export class FacilityService {
    public loadingData = new ReplaySubject(1);
    public facilityData = new ReplaySubject(1);
    public facilityInfo = new ReplaySubject(1);
    public facilityShaking = new ReplaySubject(1);
    public showInfo = new ReplaySubject(1);
    public shakingData = new ReplaySubject(1);
    public selectedFacs: Facility[] = [];
    public selection = new ReplaySubject(1);
    public filter = {};

    constructor(private _http: Http,
                private mapService: MapService) {}

    getData(filter: any = {}) {
        this.loadingData.next(true)
        let params = new URLSearchParams();
        params.set('filter', JSON.stringify(filter))
        this._http.get('/api/facility-data', {search: params})
            .map((result: Response) => result.json())
            .subscribe((result: any) => {
                this.selectedFacs = [];
                this.facilityData.next(result.data);
                this.loadingData.next(false);
            })
    }

    getShakeMapData(event: any) {
        this.loadingData.next(true)
        this._http.get('/api/shakemaps/' + event.event_id + '/facilities')
            .map((result: Response) => result.json())
            .subscribe((result: any) => {
                this.facilityData.next(result.facilities);
                this.shakingData.next(result.shaking);

                this.unselectAll();
                this.loadingData.next(false);
            })
    }

    getFacilityShaking(facility: any, event: any) {
        this.loadingData.next(true)
        this._http.get('/api/facility-shaking/' + facility['shakecast_id'] + '/' + event['event_id'])
            .map((result: Response) => result.json())
            .subscribe((result: any) => {
                if (result.data) {
                    this.facilityShaking.next(result.data);
                }
                this.loadingData.next(false)
            })
    }

    showFacInfo(fac: Facility, e: Event) {
        this.showInfo.next(fac);
        if (fac.selected) {
            e.stopPropagation();
            this.plotFac(fac)
        }
    }

    hideFacInfo() {
        this.showInfo.next(null);
    }
    
    selectAll() {
        this.selection.next('all');
    }

    unselectAll() {
        this.selection.next('none');
    }

    deleteFacs() {
        this.loadingData.next(true)
        let params = new URLSearchParams();
        params.set('inventory', JSON.stringify(this.selectedFacs))
        params.set('inventory_type', 'facility')
        this._http.delete('/api/delete/inventory', {search: params})
            .map((result: Response) => result.json())
            .subscribe((result: any) => {
                this.getData();
                this.loadingData.next(false)
            })
    }

    plotFac(fac: Facility) {
        this.facilityInfo.next(fac);
        this.mapService.plotFac(fac);
    }

    removeFac(fac: Facility) {
        this.mapService.removeFac(fac);
    }

    clearMap() {
        this.mapService.clearMap();
    }
    
}