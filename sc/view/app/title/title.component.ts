import { Component, 
         OnInit,
         OnDestroy} from '@angular/core';

import { TitleService } from './title.service';

@Component({
  selector: 'page-title',
  templateUrl: 'app/title/title.component.html',
  styleUrls: ['app/title/title.component.css']
})
export class TitleComponent implements OnInit, OnDestroy {
    private subscriptions: any[] = []
    public title: string = ''

    constructor(private titleService: TitleService) {}

    ngOnInit() {        
        this.subscriptions.push(this.titleService.title.subscribe((title: string) => {
            this.title = title
        }));}
    
    ngOnDestroy() {
        this.endSubscriptions()
    }

    endSubscriptions() {
        for (var sub in this.subscriptions) {
            this.subscriptions[sub].unsubscribe()
        }
    }
}