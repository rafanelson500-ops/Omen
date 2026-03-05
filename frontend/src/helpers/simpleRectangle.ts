import { CanvasRenderingTarget2D } from 'fancy-canvas';
import {
	type Coordinate,
	type IChartApi,
	type IPrimitivePaneRenderer,
	type IPrimitivePaneView,
	type ISeriesApi,
	type SeriesType,
	type Time,
} from 'lightweight-charts';
import { PluginBase } from '@/plugins/pluginBase';
import { positionsBox } from '@/plugins/helpers/dimensions/positions';

interface ViewPoint {
	x: Coordinate | null;
	y: Coordinate | null;
}

export interface Point {
	time: Time;
	price: number;
}

class SimpleRectanglePaneRenderer implements IPrimitivePaneRenderer {
	_p1: ViewPoint;
	_p2: ViewPoint;
	_fillColor: string;

	constructor(p1: ViewPoint, p2: ViewPoint, fillColor: string) {
		this._p1 = p1;
		this._p2 = p2;
		this._fillColor = fillColor;
	}

	draw(target: CanvasRenderingTarget2D) {
		target.useBitmapCoordinateSpace(scope => {
			if (
				this._p1.x === null ||
				this._p1.y === null ||
				this._p2.x === null ||
				this._p2.y === null
			)
				return;
			const ctx = scope.context;
			const horizontalPositions = positionsBox(
				this._p1.x,
				this._p2.x,
				scope.horizontalPixelRatio
			);
			const verticalPositions = positionsBox(
				this._p1.y,
				this._p2.y,
				scope.verticalPixelRatio
			);
			ctx.fillStyle = this._fillColor;
			ctx.fillRect(
				horizontalPositions.position,
				verticalPositions.position,
				horizontalPositions.length,
				verticalPositions.length
			);
		});
	}
}

class SimpleRectanglePaneView implements IPrimitivePaneView {
	_source: SimpleRectangle;
	_p1: ViewPoint = { x: null, y: null };
	_p2: ViewPoint = { x: null, y: null };

	constructor(source: SimpleRectangle) {
		this._source = source;
	}

	update() {
		const series = this._source.series;
		const y1 = series.priceToCoordinate(this._source._p1.price);
		const y2 = series.priceToCoordinate(this._source._p2.price);
		const timeScale = this._source.chart.timeScale();
		const x1 = timeScale.timeToCoordinate(this._source._p1.time);
		const x2 = timeScale.timeToCoordinate(this._source._p2.time);
		this._p1 = { x: x1, y: y1 };
		this._p2 = { x: x2, y: y2 };
	}

	renderer() {
		return new SimpleRectanglePaneRenderer(
			this._p1,
			this._p2,
			this._source._fillColor
		);
	}
}

/**
 * Simplified rectangle primitive optimized for HMM state visualization
 * Only includes pane view - no axis views for better performance
 */
export class SimpleRectangle extends PluginBase {
	_p1: Point;
	_p2: Point;
	_fillColor: string;
	_paneView: SimpleRectanglePaneView;

	constructor(p1: Point, p2: Point, fillColor: string) {
		super();
		this._p1 = p1;
		this._p2 = p2;
		this._fillColor = fillColor;
		this._paneView = new SimpleRectanglePaneView(this);
	}

	updateAllViews() {
		this._paneView.update();
	}

	paneViews() {
		return [this._paneView];
	}

	priceAxisViews() {
		return [];
	}

	timeAxisViews() {
		return [];
	}

	priceAxisPaneViews() {
		return [];
	}

	timeAxisPaneViews() {
		return [];
	}
}
