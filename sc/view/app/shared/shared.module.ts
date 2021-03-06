import { NgModule }            from '@angular/core';
import { CommonModule }        from '@angular/common';
import { FormsModule }         from '@angular/forms';

// Map service and component
import { MapComponent } from './maps/map.component';
import { ShakemapService } from './maps/shakemap.service.ts';

// Facility List
import { FacilityListComponent } from '../shakecast-admin/pages/facilities/facility-list.component';
import { FacilityInfoComponent } from '../shakecast-admin/pages/facilities/facility-info/facility-info.component';

// Earthquake List
import { EarthquakeListComponent } from '../shakecast/pages/earthquakes/earthquake-list.component';

// Earthquake Blurb
import { EarthquakeBlurbComponent } from './earthquake-blurb/earthquake-blurb.component';

// ng2-file-upload
import { FileSelectDirective, FileDropDirective } from 'ng2-file-upload';

// scroll behavior
import { StickToTopDirective } from './directives/stick-to-top.directive';
// screen dimmer
import { ScreenDimmerComponent } from './screen-dimmer/screen-dimmer.component';
// loading
import { LoadingComponent } from './loading/loading.component';

@NgModule({
  imports: [
        CommonModule,
        ],
  declarations: [MapComponent,
                 StickToTopDirective,
                 EarthquakeBlurbComponent,
                 ScreenDimmerComponent,
                 EarthquakeListComponent,
                 FacilityListComponent,
                 FacilityInfoComponent,
                 FileSelectDirective,
                 FileDropDirective,
                 LoadingComponent],
  providers: [
  ],
  exports: [MapComponent,
            EarthquakeBlurbComponent,
            FacilityListComponent,
            FacilityInfoComponent,
            EarthquakeListComponent,
            CommonModule, 
            FormsModule,
            StickToTopDirective,
            ScreenDimmerComponent,
            FileSelectDirective,
            FileDropDirective,
            LoadingComponent]
})
export class SharedModule { }